
from app.common.database.objects import DBBeatmap, DBBeatmapset
from app.common.database import beatmapsets, beatmaps
from app.utils import sanitize_filename
from requests import Response as HttpResponse

from fastapi.responses import StreamingResponse
from urllib.parse import quote
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Query
)

import app

router = APIRouter()

@router.get('/mt/{filename}')
@router.get('/thumb/{filename}')
@router.get('/images/map-thumb/{filename}')
def beatmap_thumbnail(
    filename: str,
    checksum: str | None = Query(None, alias='c')
) -> Response:
    key = filename.split('.', maxsplit=1)[0]
    large = 'l' in key

    set_id_string = key.removesuffix('l')

    if not set_id_string.isdigit():
        raise HTTPException(404)

    if not (image := app.session.beatmaps.background(int(set_id_string), large)):
        raise HTTPException(404)

    # Cache beatmapsets, if a checksum is given
    cache_headers = (
        {'Cache-Control': f'public, max-age={3600*24}'}
        if checksum else {}
    )

    return Response(
        image,
        media_type='image/jpeg',
        headers=cache_headers
    )

@router.get('/preview/{filename}')
@router.get('/mp3/preview/{filename}')
def beatmap_preview(
    filename: str,
    checksum: str | None = Query(None, alias='c')
) -> Response:
    key = filename.split('.', maxsplit=1)[0]

    if not key.isdigit():
        raise HTTPException(404)

    if not (mp3 := app.session.beatmaps.preview(int(key))):
        raise HTTPException(404)

    # Cache beatmapsets, if a checksum is given
    cache_headers = (
        {'Cache-Control': f'public, max-age={3600*24}'}
        if checksum else {}
    )

    return Response(
        mp3,
        media_type='audio/mpeg',
        headers=cache_headers
    )

@router.get('/d/{filename}')
@router.get('/bss/{filename}')
def beatmap_osz(filename: str) -> StreamingResponse:
    # Handle filenames such as "1 Kenji Ninuma - DISCO PRINCE.osz"
    key = filename.split(' ')[0]
    set_id_string = key.removesuffix('n')

    if not set_id_string.isdigit():
        raise HTTPException(404)

    set_id = int(set_id_string)
    no_video = 'n' in key

    if not (beatmapset := beatmapsets.fetch_one(set_id)):
        raise HTTPException(404)

    if not beatmapset.available:
        raise HTTPException(451)

    # no_video can only be true if the beatmapset has videos
    no_video = no_video and beatmapset.has_video

    if not (response := app.session.beatmaps.api.osz_response(set_id, no_video)):
        raise HTTPException(404)

    estimated_size = (
        beatmapset.osz_filesize_novideo if no_video else
        beatmapset.osz_filesize
    )
    osz_filename = sanitize_filename(
        f'{set_id} {beatmapset.artist} - {beatmapset.title}'
        f'{" (no video)" if no_video else ""}.osz'
    )

    # There's a chance we have missing osz filesizes inside the database
    # We can use the response content length to populate the missing data
    populate_osz_sizes(response, beatmapset, no_video)

    return StreamingResponse(
        response.iter_content(65536),
        media_type='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{osz_filename}"',
            'Content-Length': response.headers.get('Content-Length', f'{estimated_size}'),
            'Last-Modified': beatmapset.last_update.strftime('%a, %d %b %Y %H:%M:%S GMT')
        }
    )

@router.get('/osu/{query}')
def beatmap_file(query: str) -> Response:
    if not (beatmap := resolve_beatmap(query)):
        raise HTTPException(404)

    if not (file := app.session.beatmaps.osu(beatmap.id)):
        raise HTTPException(404)

    return Response(
        content=file,
        media_type='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{quote(beatmap.filename)}"',
            'Last-Modified': beatmap.last_update.strftime('%a, %d %b %Y %H:%M:%S GMT')
        }
    )

def resolve_beatmap(query: str) -> DBBeatmap | None:
    query = query.strip()

    if query.isdigit():
        return beatmaps.fetch_by_id(int(query))

    if query.endswith('.osu'):
        return beatmaps.fetch_by_file(query)

    return beatmaps.fetch_by_checksum(query)

def populate_osz_sizes(response: HttpResponse, beatmapset: DBBeatmapset, no_video: bool) -> None:
    target_column = 'osz_filesize_novideo' if no_video else 'osz_filesize'
    current_value = getattr(beatmapset, target_column)

    if current_value > 0:
        # Filesize was already populated
        return

    content_length = response.headers.get('Content-Length')

    if not content_length or not content_length.isdigit():
        # Most likely not in the response data
        return

    # Update the database with the new filesize
    setattr(
        beatmapset, target_column,
        int(content_length)
    )
    beatmapsets.update(
        beatmapset.id,
        {target_column: int(content_length)}
    )
