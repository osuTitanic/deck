
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.common.cache import status
from app.common.constants import DisplayMode
from app.common.database.repositories import (
    beatmapsets,
    beatmaps,
    users
)

import bcrypt
import config
import utils
import app

router = APIRouter()

@router.get('/osu-search.php')
async def search(
    legacy_password: str = Query(None, alias='c'),
    display_mode: int = Query(4, alias='r'),
    username: str = Query(None, alias='u'),
    password: str = Query(None, alias='h'),
    query: str = Query(..., alias='q')
):
    if legacy_password is None and password is None:
        # Legacy clients don't have authentication for osu! direct
        if not config.FREE_SUPPORTER:
            return '-1\nThis version of osu! does not support osu!direct'

        player = None
    else:
        if not (player := users.fetch_by_name(username)):
            return '-1\nFailed to authenticate user'

        password = password.encode() \
                if password else \
                legacy_password.encode()

        if not bcrypt.checkpw(password, player.bcrypt.encode()):
            return '-1\nFailed to authenticate user'

        if not status.exists(player.id):
            return '-1\nNot connected to bancho'

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
        results = beatmapsets.search(
            query,
            player.id if player else 0,
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
    username: str = Query(None, alias='u'),
    password: str = Query(None, alias='h'),
):
    if username and password:
        if not (player := users.fetch_by_name(username)):
            raise HTTPException(401)

        if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
            raise HTTPException(401)

        if not player.is_supporter:
            raise HTTPException(401)
    else:
        # The old clients don't use authentication for direct pickups...
        if not config.FREE_SUPPORTER:
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

