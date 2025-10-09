
from app.common.database.repositories import wrapper
from app.helpers.bss_tickets import *
from app.common import officer

from typing import Dict, Iterable
from slider import Beatmap
from osz2 import *

import bsdiff4
import gzip
import io

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
