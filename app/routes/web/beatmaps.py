
from __future__ import annotations

from typing import List, Callable, Tuple, Any
from sqlalchemy.orm import Session
from datetime import datetime

from app.common.database import users, beatmapsets, beatmaps, topics, groups, posts
from app.common.database.objects import DBUser, DBBeatmapset
from app.common.helpers import beatmaps as beatmap_helper
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
        app.session.logger.warning(f'Failed to authenticate user: User not found.')
        return error_response(5, 'Authentication failed. Please check your login credentials.'), None

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        app.session.logger.warning(f'Failed to authenticate user: Invalid password.')
        return error_response(5, 'Authentication failed. Please check your login credentials.'), None

    if player.silence_end and player.silence_end > datetime.now():
        app.session.logger.warning(f'Failed to authenticate user: User is silenced.')
        return error_response(5, 'You are not allowed to upload beatmaps while silenced.'), None

    if player.restricted:
        app.session.logger.warning(f'Failed to authenticate user: User is restricted.')
        return error_response(5, 'You are banned. Please contact support if you believe this is a mistake.'), None

    if not status.exists(player.id):
        app.session.logger.warning(f'Failed to authenticate user: User is not connected to bancho.')
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

def delete_inactive_beatmaps(user: DBUser, session: Session = ...) -> None:
    inactive_sets = beatmapsets.fetch_inactive(user.id)

    app.session.logger.debug(f'Found {len(inactive_sets)} inactive beatmapsets.')

    for set in inactive_sets:
        # Delete beatmaps
        beatmaps.delete_by_set_id(
            set.id,
            session=session
        )

    # Delete beatmapsets
    beatmapsets.delete_inactive(
        user.id,
        session=session
    )

def remaining_beatmap_uploads(user: DBUser, session: Session) -> int:
    user_groups = groups.fetch_user_groups(
        user.id,
        include_hidden=True,
        session=session
    )

    group_names = [group.name for group in user_groups]

    if 'Admins' in group_names:
        # Admins have unlimited uploads
        return 10

    unranked_beatmaps = beatmapsets.fetch_unranked_count(
        user.id,
        session=session
    )

    ranked_beatmaps = beatmapsets.fetch_ranked_count(
        user.id,
        session=session
    )

    if 'Supporter' in group_names:
        # Supporters can upload up to 8 pending maps plus
        # 1 per ranked map, up to a maximum of 12
        return (8 - unranked_beatmaps) + min(ranked_beatmaps, 12)

    # Regular users can upload up to 4 pending maps plus
    # 1 per ranked map, up to a maximum of 8
    return (4 - unranked_beatmaps) + min(ranked_beatmaps, 4)

def create_beatmapset(user: DBUser, beatmap_ids: List[int], session: Session) -> Tuple[int, List[int]]:
    # Create new beatmapset
    set = beatmapsets.create(
        id=beatmap_helper.next_beatmapset_id(session=session),
        creator=user.name,
        creator_id=user.id,
        server=1
    )

    # Create beatmaps
    new_beatmaps = [
        beatmaps.create(
            id=beatmap_helper.next_beatmap_id(session=session),
            set_id=set.id,
            session=session
        )
        for _ in beatmap_ids
    ]

    app.session.logger.info(f'Created new beatmapset ({set.id}) for user {user.name}.')

    return set.id, [beatmap.id for beatmap in new_beatmaps]

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
        app.session.logger.warning('The osz2-service url was not found. Aborting...')
        return error_response(5, 'The beatmap submission system is currently disabled. Please try again later!')

    error, user = authenticate_user(username, password, session)

    if error:
        # Failed to authenticate user
        return error

    # Delete any inactive beatmaps
    delete_inactive_beatmaps(user, session=session)

    remaining_beatmaps = remaining_beatmap_uploads(user, session)
    bubbled = False

    if (set_id > 0) and (beatmapset := beatmapsets.fetch_one(set_id, session)):
        # User wants to update an existing beatmapset
        if beatmapset.creator_id != user.id:
            app.session.logger.warning(f'Failed to update beatmapset: User does not own the beatmapset.')
            return error_response(1)

        if beatmapset.server != 1:
            app.session.logger.warning(f'Failed to update beatmapset: Beatmapset is not on Titanic.')
            return error_response(1)

        if beatmapset.status < -1:
            app.session.logger.warning(f'Failed to update beatmapset: Beatmapset is graveyarded.')
            return error_response(4)

        if beatmapset.status > 1:
            app.session.logger.warning(f'Failed to update beatmapset: Beatmapset is ranked or loved.')
            return error_response(3)

        bubbled = is_bubbled(
            beatmapset,
            session
        )

        beatmap_ids = [
            beatmap.id
            for beatmap in beatmapset.beatmaps
        ]

        app.session.logger.info(f'{user.name} wants to update a beatmapset ({set_id}).')

    else:
        # User wants to upload a new beatmapset
        if remaining_beatmaps <= 0:
            app.session.logger.warning(f'Failed to create beatmapset: User has no remaining beatmap uploads.')
            return error_response(5, "You have reached your maximum amount of beatmaps you can upload.")

        # Create a new empty beatmapset inside the database
        set_id, beatmap_ids = create_beatmapset(
            user,
            beatmap_ids,
            session=session
        )

        if set_id is None:
            return error_response(5, "An error occurred while creating the beatmapset.")

    # Either we don't have the osz2 file or the client has no osz2 file
    # If full-submit is true, the client will submit a patch file
    full_submit = (
        not app.session.storage.file_exists(f'{set_id}', 'osz2')
        or not osz2_hash
    )

    # NOTE: In theory we could always set this to true, so we don't have
    #       to store the osz2 files, but i've decided against this

    return Response('\n'.join([
        '0',
        f'{set_id}',
        ','.join(map(str, beatmap_ids)),
        f'{int(full_submit)}',
        f'{remaining_beatmaps}',
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

@router.get('/osu-get-beatmap-topic.php')
def topic_contents(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='s')
):
    error, user = authenticate_user(username, password, session)

    if error:
        # Failed to authenticate user
        return error

    if not (beatmapset := beatmapsets.fetch_one(set_id, session)):
        app.session.logger.warning(f'Failed to fetch beatmapset topic: Beatmapset not found.')
        return error_response(1)

    if not (topic := topics.fetch_one(beatmapset.topic_id, session)):
        app.session.logger.warning(f'Failed to fetch beatmapset topic: Topic not found.')
        return error_response(1)

    first_post = posts.fetch_initial_post(topic.id, session)

    return Response('3'.join([
        f'0',
        f'{topic.id}',
        f'{topic.title}',
        f'{first_post.content if first_post else ""}',
    ]))
