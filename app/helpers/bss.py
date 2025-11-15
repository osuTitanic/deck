
from app.common.constants import BeatmapGenre, BeatmapLanguage
from app.common.database import DBBeatmapset, DBBeatmap
from app.common.database.repositories import wrapper
from app.helpers.bss_tickets import *
from app.helpers.bss_osz2 import *

from zipfile import ZipFile, ZipInfo
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from slider import Beatmap
from enum import IntEnum
from typing import List
from osz2 import *

import statistics
import hashlib
import zipfile
import io

class SendAction(IntEnum):
    Standard = 0
    FirstBeatmap = 1
    LastBeatmap = 2
    SingleBeatmap = 3

    @classmethod
    def values(cls) -> list:
        return list(cls._value2member_map_.keys())

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

LanguageMapping = {
    BeatmapLanguage(language_id).name.lower(): BeatmapLanguage(language_id)
    for language_id in BeatmapLanguage.values()
}

GenreMapping = {
    BeatmapGenre(genre_id).name.lower(): BeatmapGenre(genre_id)
    for genre_id in BeatmapGenre.values()
}

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
        # Create ZipInfo to set file metadata
        zip_info = ZipInfo(filename=file.filename)
        zip_info.compress_type = zipfile.ZIP_DEFLATED
        zip_info.date_time = file.date_modified.timetuple()[:6]
        osz.writestr(zip_info, file.content)

    osz.close()
    result = buffer.getvalue()

    del buffer
    del osz
    return result

def calculate_osz_size(files: List[File]) -> int:
    """Calculate the size of an .osz package from a list of files"""
    return len(create_osz_package(files))

def osz_to_files(osz_data: bytes) -> List[File]:
    """Extract files from an .osz package into osz2.File objects"""
    with ZipFile(io.BytesIO(osz_data)) as zip_file:
        files = []

        for info in zip_file.infolist():
            content = zip_file.read(info.filename)
            content_hash = hashlib.md5(content).digest()

            file = File(
                filename=info.filename,
                content=content,
                offset=info.header_offset,
                size=info.file_size,
                hash=content_hash,
                date_created=datetime(*info.date_time),
                date_modified=datetime(*info.date_time)
            )
            files.append(file)

    return files

def detect_language_from_tags(tags: List[str]) -> BeatmapLanguage:
    for tag in tags:
        filtered_tag = tag.lower().strip(",").strip()

        if language := LanguageMapping.get(filtered_tag):
            return language

    return BeatmapLanguage.Unspecified

def detect_genre_from_tags(tags: List[str]) -> BeatmapGenre:
    for tag in tags:
        filtered_tag = tag.lower().strip(",").strip()

        if genre := GenreMapping.get(filtered_tag):
            return genre

    return BeatmapGenre.Unspecified

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
