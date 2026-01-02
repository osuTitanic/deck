
from app.common.config import config_instance as config
from app.common.database import DBBeatmapset, DBUser
from app.common.constants import DirectDisplayMode
from app.utils import sanitize_filename
from app.common.cache import status
from app.common import officer
from app.common.database import (
    beatmapsets,
    beatmaps,
    users,
    posts
)

from typing import Callable, Generator
from sqlalchemy.orm import Session
from functools import wraps
from fastapi import (
    HTTPException,
    APIRouter,
    Depends,
    Query
)

import app

router = APIRouter()
post_id_mapping: dict[int, int] = {}

def direct_error(message: str) -> str:
    return f"-1\n{message}"

def direct_authentication(username: str | None, password: str | None, session: Session) -> DBUser | None:
    if not username or not password:
        return

    if not (player := users.fetch_by_name(username, session)):
        return

    if not app.utils.check_password(password, player.bcrypt):
        return

    if not player.is_supporter:
        return

    return player

def direct_beatmap(set: DBBeatmapset, post_id: int = 0) -> str:
    versions = ",".join(
        (f"{beatmap.version}@{beatmap.mode}" for beatmap in set.beatmaps)
    )

    return "|".join([
        sanitize_filename(f'{set.id} {set.full_name}.osz'),
        set.artist  if set.artist else "",
        set.title   if set.title else "",
        set.creator if set.creator else "",
        str(set.status),
        str(set.rating_average),
        str(set.last_update),
        str(set.id),
        str(set.topic_id or 0),
        str(int(set.has_video)),
        str(int(set.has_storyboard)),
        str(set.osz_filesize),
        str(set.osz_filesize_novideo),
        versions,
        str(post_id or 0),
    ])

def resolve_post_id(topic_id: int | None, session: Session) -> int:
    if not topic_id:
        return 0

    if topic_id in post_id_mapping:
        return post_id_mapping[topic_id]

    post_id = posts.fetch_initial_post_id(topic_id, session)
    post_id_mapping[topic_id] = post_id
    return post_id

def catch_direct_errors(func) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs) -> str:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            officer.call(f'Failed to execute {func.__name__}.', exc_info=e)
            return direct_error('A server error occurred. Please try again!')
    return wrapper

@router.get('/osu-search.php')
@catch_direct_errors
def search(
    session: Session = Depends(app.session.database.yield_session),
    display_mode: DirectDisplayMode = Query(DirectDisplayMode.All, alias='r'),
    legacy_password: str | None = Query(None, alias='c'),
    page_offset: int | None = Query(None, alias='p'),
    username: str | None = Query(None, alias='u'),
    password: str | None = Query(None, alias='h'),
    query: str = Query(..., alias='q'),
    mode: int = Query(-1, alias='m')
) -> str:
    player = direct_authentication(
        username,
        password or legacy_password,
        session
    )

    if player is None and not config.ALLOW_UNAUTHENTICATED_DIRECT:
        return direct_error('This version of osu! is not supported.')

    if len(query) < 2:
        return direct_error('Query is too short.')

    client = (
        status.version(player.id) or 0
        if player is not None else 0
    )

    # Prior to b20140315.9, setting the "m" parameter to 0 
    # meant "all modes", instead of only osu! standard
    if mode == 0 and client <= 20140315:
        mode = -1

    app.session.logger.info(
        f'Got osu!direct search request: "{query}" '
        f'from "{player}"'
    )

    supports_page_offset = page_offset is not None
    page_offset = page_offset or 0
    response = []

    results = beatmapsets.search_direct(
        query,
        player.id if player else 0,
        display_mode,
        mode,
        limit=100,
        offset=page_offset * 100,
        session=session
    )

    if not supports_page_offset:
        response.append(str(
            len(results)
        ))

    else:
        response.append(str(
            len(results)
            if len(results) < 100 else 101
        ))

    for set in results:
        post_id = resolve_post_id(set.topic_id, session)
        response.append(direct_beatmap(set, post_id))

    return "\n".join(response)

@router.get('/osu-search-set.php')
def pickup_info(
    session: Session = Depends(app.session.database.yield_session),
    beatmap_id: int | None = Query(None, alias='b'),
    topic_id: int | None = Query(None, alias='t'),
    checksum: str | None = Query(None, alias='c'),
    post_id: int | None = Query(None, alias='p'),
    set_id: int | None = Query(None, alias='s'),
    username: str | None = Query(None, alias='u'),
    password: str | None = Query(None, alias='h'),
) -> str:
    player = direct_authentication(username, password, session)
    beatmapset: DBBeatmapset | None = None

    if player is None and not config.ALLOW_UNAUTHENTICATED_DIRECT:
        raise HTTPException(401)

    if set_id:
        beatmapset = beatmapsets.fetch_one(set_id, session)

    if beatmap_id:
        beatmap = beatmaps.fetch_by_id(beatmap_id, session)
        beatmapset = beatmap.beatmapset if beatmap else None

    if checksum:
        beatmap = beatmaps.fetch_by_checksum(checksum, session)
        beatmapset = beatmap.beatmapset if beatmap else None

    if post_id:
        topic_id = posts.fetch_topic_id(post_id, session)

    if topic_id:
        beatmapset = beatmapsets.fetch_by_topic(topic_id, session)

    if not beatmapset:
        app.session.logger.warning("osu!direct pickup request failed: Not found")
        raise HTTPException(404)

    if beatmapset.status == -3:
        # Beatmap was deleted or has not been submitted yet
        app.session.logger.warning("osu!direct pickup request failed: Inactive beatmapset")
        raise HTTPException(404)

    app.session.logger.info(
        f'{player} -> '
        f'Got osu!direct pickup request for: "{beatmapset.full_name}".'
    )

    return direct_beatmap(
        beatmapset,
        resolve_post_id(beatmapset.topic_id, session)
    )
