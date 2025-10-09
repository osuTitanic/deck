
from app.common.constants import BeatmapGenre, BeatmapLanguage
from app.common.database import DBBeatmapset, DBBeatmap
from app.common.database.repositories import wrapper
from app.helpers.bss_tickets import *
from app.common import officer

from typing import List, Dict, Iterable
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from zipfile import ZipFile
from slider import Beatmap
from osz2 import *

import statistics
import hashlib
import zipfile
import bsdiff4
import gzip
import io

allowed_file_extensions = (
    ".osu", ".osz", ".osb", ".osk", ".png", ".mp3", ".jpeg",
    ".wav", ".png", ".wav", ".ogg", ".jpg", ".wmv", ".flv",
    ".mp3", ".flac", ".mp4", ".avi", ".ini", ".jpg", ".m4v",
    ".mpg", ".mov", ".webm", ".mkv", ".ogv", ".mpeg", ".3gp"
)

video_file_extensions = (
    ".wmv", ".flv", ".mp4",
    ".avi", ".m4v", ".mpg",
    ".mov", ".webm", ".mkv",
    ".ogv", ".mpeg", ".3gp"
)

class InternalOsz2(Osz2Package):
    """An extension of the osz2 package that implements beatmap parsing with slider"""
    def __init__(
        self,
        reader: io.BufferedReader,
        metadata_only=False,
        key_type=KeyType.OSZ2
    ) -> None:
        super().__init__(reader, metadata_only, key_type)
        self.beatmaps: Dict[str, Beatmap] = {}
        
        if not metadata_only:
            self.populate_beatmaps()

    @property
    def beatmap_files(self) -> Iterable[File]:
        for file in self.files:
            if file.filename.endswith(".osu"):
                yield file

    def populate_beatmaps(self) -> None:
        for file in self.beatmap_files:
            beatmap = parse_beatmap(file.content)

            if beatmap:
                self.beatmaps[file.filename] = beatmap

def process_on_fail(e: Exception) -> None:
    officer.call(f'Failed to process osz/osu file: "{e}"')
    raise e

@wrapper.exception_wrapper(process_on_fail)
def decrypt_osz2(osz2_file: bytes) -> InternalOsz2 | None:
    return InternalOsz2.from_bytes(osz2_file)

@wrapper.exception_wrapper(process_on_fail)
def patch_osz2(osz2_patch: bytes, osz2_source: bytes) -> bytes | None:
    return bsdiff4.core.patch(osz2_source, *read_gzip_patch(osz2_patch))

@wrapper.exception_wrapper(process_on_fail)
def parse_beatmap(osu_file: bytes) -> Beatmap | None:
    return Beatmap.parse(osu_file.decode(errors='ignore'))

@wrapper.exception_wrapper(process_on_fail)
def osz2_metadata_from_beatmap(beatmap: Beatmap) -> Dict[str, str]:
    return {
        MetadataType.Title.name: beatmap.title,
        MetadataType.TitleUnicode.name: beatmap.title_unicode,
        MetadataType.Artist.name: beatmap.artist,
        MetadataType.ArtistUnicode.name: beatmap.artist_unicode,
        MetadataType.Creator.name: beatmap.creator,
        MetadataType.Source.name: beatmap.source,
        MetadataType.Tags.name: ' '.join(beatmap.tags),
        MetadataType.PreviewTime.name: beatmap.preview_time.total_seconds()
    }

def read_gzip_patch(patch_bytes: bytes, compressor=gzip) -> tuple:
    """
    Read a BSDIFF4-format patch from bytes 'patch_bytes'
    with control over the compression algorithm.
    (osu! uses gzip compression for its patches)
    """
    fi = io.BytesIO(patch_bytes)
    magic = fi.read(8)

    if magic[:7] != b'BSDIFF40'[:7]:
        raise ValueError("incorrect magic bsdiff4 header")

    # length headers
    len_control = bsdiff4.core.decode_int64(fi.read(8))
    len_diff = bsdiff4.core.decode_int64(fi.read(8))
    len_dst = bsdiff4.core.decode_int64(fi.read(8))

    # read the control header
    bcontrol = compressor.decompress(fi.read(len_control))
    tcontrol = [
        (bsdiff4.core.decode_int64(bcontrol[i:i + 8]),
         bsdiff4.core.decode_int64(bcontrol[i + 8:i + 16]),
         bsdiff4.core.decode_int64(bcontrol[i + 16:i + 24]))
         for i in range(0, len(bcontrol), 24)
    ]

    # read the diff and extra blocks
    bdiff = compressor.decompress(fi.read(len_diff))
    bextra = compressor.decompress(fi.read())
    return len_dst, tcontrol, bdiff, bextra

@wrapper.session_wrapper
def next_beatmapset_id(session: Session = ...) -> int:
    """Get the next availabe beatmapset id"""
    while True:
        database_id = session.query(
            func.nextval('beatmapsets_id_seq')
        ).scalar()

        exists = session.query(DBBeatmapset.id) \
            .filter(DBBeatmapset.id == database_id) \
            .count() > 0

        if exists:
            continue

        return database_id

@wrapper.session_wrapper
def next_beatmap_id(session: Session = ...) -> int:
    """Get the next availabe beatmap id"""
    while True:
        database_id = session.query(
            func.nextval('beatmaps_id_seq')
        ).scalar()

        exists = session.query(DBBeatmap.id) \
            .filter(DBBeatmap.id == database_id) \
            .count() > 0

        if exists:
            continue

        return database_id

# Reference:
# https://github.com/ppy/osu/blob/master/osu.Game/Beatmaps/Timing/BreakPeriod.cs

# The minimum gap between the start of the break and the previous object.
gap_before_break = 200

# The minimum gap between the end of the break and the next object.
gap_after_break = 450

# The minimum duration required for a break to have any effect.
min_break_duration = 650

# The minimum required duration of a gap between two objects such that a break can be placed between them.
minimum_gap = gap_before_break + min_break_duration + gap_after_break

def calculate_beatmap_total_length(beatmap: Beatmap) -> int:
    """Calculate the total length of a beatmap from its hit objects"""
    hit_objects = beatmap.hit_objects()

    if len(hit_objects) <= 1:
        return 0

    last_object = hit_objects[-1].time.total_seconds() * 1000
    first_object = hit_objects[0].time.total_seconds() * 1000
    return last_object - first_object

def calculate_beatmap_drain_length(beatmap: Beatmap) -> int:
    """Calculate the drain length of a beatmap from its hit objects"""
    hit_objects = beatmap.hit_objects()

    if len(hit_objects) <= 1:
        return 0

    # Identify every break in the beatmap
    # and subtract it from the total length
    total_length = calculate_beatmap_total_length(beatmap)
    break_deltas = []

    for index, hit_object in enumerate(hit_objects):
        if index <= 0:
            continue
        
        previous_object = hit_objects[index - 1]
        delta_time = hit_object.time - previous_object.time
        delta_time_seconds = delta_time.total_seconds() * 1000
        
        if delta_time_seconds <= minimum_gap:
            continue

        break_deltas.append(delta_time_seconds - (gap_before_break + gap_after_break))
        
    total_break_time = sum(break_deltas)
    return max(total_length - total_break_time, 0)

def calculate_beatmap_median_bpm(beatmap: Beatmap) -> float:
    """Calculate the median BPM of a beatmap from its timing points"""
    bpm_values = (p.bpm for p in beatmap.timing_points if p.bpm)

    if not bpm_values:
        return 0.0

    return statistics.median(bpm_values)

def maximum_beatmap_length(beatmaps: List[Beatmap]) -> int:
    """Retrieve the maximum total length of all beatmaps in milliseconds"""
    if not beatmaps:
        return 0

    return max(
        calculate_beatmap_total_length(beatmap)
        for beatmap in beatmaps
    )

def calculate_size_limit(beatmap_length: int) -> int:
    # The file size limit is 10MB plus an additional 10MB for
    # every minute of beatmap length, and it caps at 100MB.
    return min(
        10_000_000 + (10_000_000 * (beatmap_length / 60)),
        100_000_000
    )

def create_osz_package(files: List[File]) -> bytes:
    """Create an .osz package from a list of files"""
    buffer = io.BytesIO()
    osz = ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED)

    for file in files:
        # TODO: Use ZipInfo to set file date(s)
        osz.writestr(file.filename, file.content)

    osz.close()
    result = buffer.getvalue()

    del buffer
    del osz
    return result

def calculate_osz_size(files: List[File]) -> int:
    """Calculate the size of an .osz package from a list of files"""
    return len(create_osz_package(files))

def osz_to_files(osz_data: bytes) -> List[File]:
    with ZipFile(io.BytesIO(osz_data)) as zip_file:
        files = []

        for info in zip_file.infolist():
            content = zip_file.read(info.filename)
            content_hash = hashlib.md5(content).digest()

            files.append(
                File(
                    filename=info.filename,
                    content=content,
                    offset=info.header_offset,
                    size=info.file_size,
                    hash=content_hash,
                    date_created=datetime(*info.date_time),
                    date_modified=datetime(*info.date_time)
                )
            )

    return files

LanguageDict = {
    BeatmapLanguage(language_id).name.lower(): BeatmapLanguage(language_id)
    for language_id in BeatmapLanguage.values()
}

GenreDict = {
    BeatmapGenre(genre_id).name.lower(): BeatmapGenre(genre_id)
    for genre_id in BeatmapGenre.values()
}

def detect_language_from_tags(tags: List[str]) -> BeatmapLanguage:
    for tag in tags:
        filtered_tag = tag.lower().strip(",").strip()

        if language := LanguageDict.get(filtered_tag):
            return language

    return BeatmapLanguage.Unspecified

def detect_genre_from_tags(tags: List[str]) -> BeatmapGenre:
    for tag in tags:
        filtered_tag = tag.lower().strip(",").strip()

        if genre := GenreDict.get(filtered_tag):
            return genre

    return BeatmapGenre.Unspecified
