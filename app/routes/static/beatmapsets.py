
from app.common.database.repositories import beatmapsets
from fastapi.responses import StreamingResponse
from fastapi import (
    HTTPException,
    APIRouter,
    Response
)

import app

router = APIRouter()

@router.get('/mt/{filename}')
@router.get('/thumb/{filename}')
@router.get('/images/map-thumb/{filename}')
def beatmap_thumbnail(filename: str):
    key = filename.split('.', maxsplit=1)[0]

    if not (image := app.session.storage.get_background(key)):
        raise HTTPException(404)

    set_id = int(key.removesuffix('l'))

    # Cache beatmapsets from bancho
    cache_response = set_id < 1000000000
    cache_expiry = 3600*24
    cache_headers = (
        {'Cache-Control': f'public, max-age={cache_expiry}'}
        if cache_response else {}
    )

    return Response(
        image,
        media_type='image/jpeg',
        headers=cache_headers
    )

@router.get('/preview/{filename}')
@router.get('/mp3/preview/{filename}')
def beatmap_preview(filename: str):
    key = filename.split('.', maxsplit=1)[0]

    if not key.isdigit():
        raise HTTPException(404)

    if not (mp3 := app.session.storage.get_mp3(key)):
        raise HTTPException(404)

    # Cache beatmapsets from bancho
    set_id = int(key)
    cache_response = set_id < 1000000000
    cache_expiry = 3600*24
    cache_headers = (
        {'Cache-Control': f'public, max-age={cache_expiry}'}
        if cache_response else {}
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

    if not (response := app.session.storage.api.osz(set_id, no_video)):
        raise HTTPException(404)

    return StreamingResponse(
        response.iter_content(6400),
        media_type='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{set_id} {beatmapset.artist} - {beatmapset.title}.osz"',
            'Content-Length': response.headers.get('Content-Length', 0)
        }
    )
