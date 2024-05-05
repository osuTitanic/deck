
from __future__ import annotations

from typing import List, Callable, Tuple, Any
from sqlalchemy.orm import Session
from datetime import datetime

from app.common.database.objects import DBUser, DBBeatmapset
from app.common.database import users, beatmapsets, topics
from app.common.cache import status

from fastapi import (
    UploadFile,
    APIRouter,
    Response,
    Request,
    Depends,
    Query,
    Form,
    File
)

import bcrypt
import config
import app

router = APIRouter()

def comma_list(parameter: str, cast=str) -> Callable:
    async def wrapper(request: Request) -> List[Any]:
        query = request.query_params.get(parameter, '')
        return [cast(value) for value in query.split(',')]
    return wrapper

def integer_boolean(parameter: str) -> Callable:
    async def wrapper(request: Request) -> bool:
        query = request.query_params.get(parameter, '0')
        return query == '1'
    return wrapper

def integer_boolean_form(parameter: str) -> Callable:
    async def wrapper(request: Request) -> bool:
        form = await request.form()
        query = form.get(parameter, '0')
        return query == '1'
    return wrapper

def error_response(error_code: int, message: str = "") -> Response:
    return Response(f'{error_code}\n{message}')

def authenticate_user(
    username: str,
    password: str,
    session: Session
) -> Tuple[Response, DBUser]:
    player = users.fetch_by_name(username, session=session)

    if not player:
        return error_response(5, 'Authentication failed. Please check your login credentials.'), None

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        return error_response(5, 'Authentication failed. Please check your login credentials.'), None

    if player.silence_end and player.silence_end > datetime.now():
        return error_response(5, 'You are not allowed to upload beatmaps while silenced.'), None

    if player.restricted:
        return error_response(5, 'You are banned. Please contact support if you believe this is a mistake.'), None

    if not status.exists(player.id):
        return error_response(5, 'You are not connected to bancho, please try again!'), None

    return None, player

def is_bubbled(beatmapset: DBBeatmapset, session: Session) -> bool:
    topic = topics.fetch_one(
        beatmapset.topic_id,
        session=session
    )

    return (
        topic.icon_id == 3
        if topic else False
    )

def delete_upload_tickets(user: DBUser) -> None:
    # TODO: Delete all upload tickets for the user
    ...

def remaining_beatmap_uploads(user: DBUser, session: Session) -> int:
    # TODO: Calculate the remaining beatmap uploads
    ...

def create_upload_ticket(user: DBUser, session: Session) -> int:
    # TODO: Add a ticket to the cache
    ...

def update_beatmap_ids(set_id: int, beatmap_ids: List[int], session: Session) -> List[int]:
    # TODO: Validate & update the beatmap ids
    ...

@router.get('/osu-osz2-bmsubmit-getid.php')
def validate_upload_request(
    session: Session = Depends(app.session.database.yield_session),
    beatmap_ids: List[int] = Depends(comma_list('b', int)),
    osz2_hash: str = Query(..., alias='z'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='s')
) -> Response:
    if not config.OSZ2_SERVICE_URL:
        return error_response(5, 'Beatmap submission was disabled by an admin.')

    error, user = authenticate_user(username, password, session)

    if error:
        return error

    # Delete any previous upload tickets
    delete_upload_tickets(user)

    remaining_beatmaps = remaining_beatmap_uploads(user, session)
    bubbled = False

    if (set_id > 0) and (beatmapset := beatmapsets.fetch_one(set_id, session)):
        # User wants to update an existing beatmapset
        if beatmapset.creator_id != user.id:
            # User doesn't own this beatmapset
            return error_response(1)

        if beatmapset.status < -1:
            # Beatmapset is in Graveyard
            return error_response(4)

        if beatmapset.status > 1:
            # Beatmapset is already ranked
            return error_response(3)

        bubbled = is_bubbled(beatmapset, session)

    else:
        # User wants to upload a new beatmapset
        if remaining_beatmaps <= 0:
            return error_response(5, "You have reached your maximum amount of beatmaps you can upload.")

        # Create a new beatmapset ticket inside the cache
        set_id = create_upload_ticket(user, session)

    # Either we don't have the file or the client has no package
    full_submit = (
        not app.session.storage.file_exists(f'{set_id}', 'osz2')
        or osz2_hash == '0'
    )

    beatmap_ids = update_beatmap_ids(set_id, beatmap_ids, session)

    return Response('\n'.join([
        '0',
        f'{set_id}',
        ','.join(beatmap_ids),
        f'{int(full_submit)}',
        f'{int(bubbled)}'
    ]))

@router.post('/osu-osz2-bmsubmit-upload.php')
def upload_beatmap(
    full_submit: bool = Depends(integer_boolean('t')),
    osz2_file: UploadFile = File(..., alias='osz2'),
    osz2_hash: str = Query(..., alias='z'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='s')
):
    # Actually uploads the beatmap
    ...

@router.post('/osu-osz2-bmsubmit-post.php')
def forum_post(
    username: str = Form(..., alias='u'),
    password: str = Form(..., alias='p'),
    set_id: int = Form(..., alias='b'),
    subject: str = Form(...),
    message: str = Form(...),
    complete: bool = Depends(integer_boolean_form('complete')),
    notify: bool = Depends(integer_boolean_form('notify'))
):
    # Creates the forum post and returns its threadId
    ...
