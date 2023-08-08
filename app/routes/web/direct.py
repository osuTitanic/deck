
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from app.common.constants import DisplayMode
from app.common.database.repositories import (
    beatmapsets,
    beatmaps,
    users
)

import bcrypt
import utils
import app

router = APIRouter()

@router.get('/osu-search.php')
def search(
    display_mode: int = Query(4, alias='r'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    query: str = Query(..., alias='q')
):
    if not (player := users.fetch_by_name(username)):
        return '-1\nFailed to authenticate user'

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        return '-1\nFailed to authenticate user'

    if not player.is_supporter:
        return "-1\nWhy are you here?"

    try:
        display_mode = DisplayMode(display_mode)
    except ValueError:
        return "-1\nno."

    if len(query) < 3:
        return "-1\nQuery is too short."

    response = []

    try:
        # This searching algorythm is really bad, but
        # it works for now at least...
        results = beatmapsets.search(
            query,
            player.id,
            display_mode
        )

        response.append(str(
            len(results)
        ))

        for set in results:
            response.append(
                utils.online_beatmap(set)
            )
    except Exception as e:
        app.session.logger.error(f'Failed to execute search: {e}')
        return "-1\nServer error. Please try again!"

    return "\n".join(response)

@router.get('/osu-search-set.php')
def pickup_info(
    beatmap_id: Optional[int] = Query(None, alias='b'),
    topic_id: Optional[int] = Query(None, alias='t'),
    checksum: Optional[int] = Query(None, alias='c'),
    post_id: Optional[int] = Query(None, alias='p'),
    set_id: Optional[int] = Query(None, alias='s'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
):
    if not (player := users.fetch_by_name(username)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    if not player.is_supporter:
        raise HTTPException(401)

    if topic_id:
        # TODO
        raise HTTPException(404)

    if post_id:
        # TODO
        raise HTTPException(404)

    if beatmap_id:
        beatmap = beatmaps.fetch_by_id(beatmap_id)
        beatmapset = beatmap.beatmapset if beatmap else None

    if checksum:
        beatmap = beatmaps.fetch_by_checksum(checksum)
        beatmapset = beatmap.beatmapset if beatmap else None

    if set_id:
        beatmapset = beatmapsets.fetch_one(set_id)

    if not beatmapset:
        raise HTTPException(404)

    if not beatmapset.osz_filesize:
        utils.update_osz_filesize(
            beatmapset.id, 
            beatmapset.has_video
        )

    return utils.online_beatmap(beatmapset)

