
from __future__ import annotations
from app.common.database import beatmapsets

from fastapi.responses import StreamingResponse
from fastapi import (
    HTTPException,
    APIRouter,
    Response
)

import app

router = APIRouter()

@router.get('/mt/{id}')
@router.get('/thumb/{id}')
@router.get('/images/map-thumb/{id}')
def beatmap_thumbnail(id: str):
    id = id.removesuffix('.jpg')

    if not (image := app.session.storage.get_background(id)):
        return

    return Response(image, media_type='image/jpeg')

@router.get('/preview/{filename}')
@router.get('/mp3/preview/{filename}')
def beatmap_preview(filename: str):
    set_id = int(filename.replace('.mp3', ''))

    if not (mp3 := app.session.storage.get_mp3(set_id)):
        return

    return Response(mp3, media_type='audio/mpeg')

@router.get('/d/{id}')
def beatmap_osz(id: str):
    if not id.replace('n', '').isdigit():
        raise HTTPException(400)

    set_id = int(id.replace('n', ''))
    no_video = 'n' in id

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
