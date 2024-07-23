
from __future__ import annotations

from app.common.database.repositories import beatmapsets
from app.routes import avatar

from fastapi.responses import StreamingResponse
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Request
)

import app

router = APIRouter()

@router.get('/mt/{id}')
@router.get('/thumb/{id}')
@router.get('/images/map-thumb/{id}')
def direct_cover(id: str):
    id = id.removesuffix('.jpg')

    if not (image := app.session.storage.get_background(id)):
        return

    return Response(image)

@router.get('/preview/{filename}')
@router.get('/mp3/preview/{filename}')
def mp3(filename: str):
    set_id = int(filename.replace('.mp3', ''))

    if not (mp3 := app.session.storage.get_mp3(set_id)):
        return

    return Response(mp3)

@router.get('/d/{id}')
def osz(id: str):
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
            'Content-Disposition': f'attachment; filename={set_id} {beatmapset.artist} - {beatmapset.title}.osz',
            'Content-Length': response.headers.get('Content-Length', 0)
        }
    )

@router.get('/forum/download.php')
def legacy_avatar(request: Request):
    args = request.query_params

    if not (filename := args.get('avatar')):
        return avatar.default_avatar()

    return avatar.avatar(str(filename), None, None)
