
from fastapi.responses import StreamingResponse
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Request,
    Query
)

from app.common.database.repositories import users
from app.common.database import DBBeatmapset

from . import avatar

import bcrypt
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
def osz(
    id: str,
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h')
):
    if not (user := users.fetch_by_name(username)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), user.bcrypt.encode()):
        raise HTTPException(401)

    set_id = int(id.replace('n', ''))
    no_video = 'n' in id

    if not (response := app.session.storage.api.osz(set_id, no_video)):
        return

    osz = response.iter_content(1024)

    if filesize := response.headers.get('Content-Length'):
        instance = app.session.database.session
        instance.query(DBBeatmapset) \
            .filter(DBBeatmapset.id == set_id) \
            .update({
                f'osz_filesize{"_novideo" if no_video else ""}': filesize,
                'available': True
            })
        instance.commit()

    return StreamingResponse(osz)

@router.get('/images/achievements/{filename}')
def achievement_image(filename: str):
    if not (image := app.session.storage.get_achievement(filename)):
        raise HTTPException(404)

    return Response(image)

@router.get('/forum/download.php')
def legacy_avatar(request: Request):
    args = request.query_params

    if not (filename := args.get('avatar')):
        return avatar.default_avatar()

    return avatar.avatar(str(filename))

# TODO: Move to seperate server
