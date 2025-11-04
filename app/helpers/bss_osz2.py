
from app.common.database.repositories import wrapper
from app.helpers.bss_tickets import *
from app.common import officer

from io import BufferedReader
from slider import Beatmap
from typing import Dict
from osz2 import *

class InternalOsz2(Osz2Package):
    """An extension of the osz2 package that implements beatmap parsing with slider"""
    def __init__(
        self,
        reader: BufferedReader,
        metadata_only=False,
        key_type=KeyType.OSZ2
    ) -> None:
        super().__init__(reader, metadata_only, key_type)
        self.beatmaps: Dict[str, Beatmap] = {}
        
        if not metadata_only:
            self.populate_beatmaps()

    def populate_beatmaps(self) -> None:
        for file in self.beatmap_files:
            beatmap = parse_beatmap(file.content)

            if beatmap:
                self.beatmaps[file.filename] = beatmap

def process_on_fail(e: Exception) -> None:
    officer.call(f'Failed to process osz/osu file: "{e}"')

@wrapper.exception_wrapper(process_on_fail)
def decrypt_osz2(osz2_file: bytes) -> InternalOsz2 | None:
    return InternalOsz2.from_bytes(osz2_file)

@wrapper.exception_wrapper(process_on_fail)
def patch_osz2(osz2_patch: bytes, osz2_source: bytes) -> bytes | None:
    return apply_bsdiff_patch(osz2_source, osz2_patch)

@wrapper.exception_wrapper(process_on_fail)
def parse_beatmap(osu_file: bytes) -> Beatmap | None:
    return Beatmap.parse(osu_file.decode(encoding='utf-8-sig', errors='ignore'))

@wrapper.exception_wrapper(process_on_fail)
def osz2_metadata_from_beatmap(beatmap: Beatmap) -> Dict[MetadataType, str]:
    return {
        MetadataType.Title: beatmap.title,
        MetadataType.TitleUnicode: beatmap.title_unicode,
        MetadataType.Artist: beatmap.artist,
        MetadataType.ArtistUnicode: beatmap.artist_unicode,
        MetadataType.Creator: beatmap.creator,
        MetadataType.Source: beatmap.source,
        MetadataType.Tags: ' '.join(beatmap.tags),
        MetadataType.PreviewTime: beatmap.preview_time.total_seconds()
    }
