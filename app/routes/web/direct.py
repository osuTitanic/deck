
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.common.cache import status
from app.common.database import DBBeatmapset
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
def search(
    legacy_password: str = Query(None, alias='c'),
    display_mode: int = Query(4, alias='r'),
    username: str = Query(None, alias='u'),
    password: str = Query(None, alias='h'),
    query: str = Query(..., alias='q')
):
    player = None

    with app.session.database.managed_session() as session:
        if legacy_password is None and password is None:
            # NOTE: Old clients don't have authentication for osu! direct
            if not config.FREE_SUPPORTER:
                return '-1\nThis version of osu! does not support osu!direct'

        else:
            if not (player := users.fetch_by_name(username, session)):
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

        if display_mode not in DisplayMode._value2member_map_:
            return "-1\nInvalid display mode"

        display_mode = DisplayMode(display_mode)

        if len(query) < 2:
            return "-1\nQuery is too short."

        app.session.logger.info(
            f'Got osu!direct search request: "{query}" '
            f'from "{player.name}"' if player else ''
        )

        response = []

        try:
            results = beatmapsets.search(
                query,
                player.id if player else 0,
                display_mode,
                session
            )

            response.append(str(
                len(results)
            ))

            for set in results:
                response.append(
                    utils.online_beatmap(set)
                )
        except Exception as e:
            app.session.logger.error(f'Failed to execute search: {e}', exc_info=e)
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
    with app.session.database.managed_session() as session:
        if username and password:
            if not (player := users.fetch_by_name(username, session)):
                raise HTTPException(401)

            if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
                raise HTTPException(401)

            if not player.is_supporter:
                raise HTTPException(401)
        else:
            # NOTE: Old clients don't use authentication for direct pickups
            if not config.FREE_SUPPORTER:
                raise HTTPException(401)

        if topic_id:
            # TODO
            raise HTTPException(404)

        if post_id:
            # TODO
            raise HTTPException(404)

        beatmapset: Optional[DBBeatmapset] = None

        if beatmap_id:
            beatmap = beatmaps.fetch_by_id(beatmap_id, session)
            beatmapset = beatmap.beatmapset if beatmap else None

        if checksum:
            beatmap = beatmaps.fetch_by_checksum(checksum, session)
            beatmapset = beatmap.beatmapset if beatmap else None

        if set_id:
            beatmapset = beatmapsets.fetch_one(set_id, session)

        if not beatmapset:
            app.session.logger.warning("osu!direct pickup request failed: Not found")
            raise HTTPException(404)

        app.session.logger.info(
            f'Got osu!direct pickup request for: "{beatmapset.full_name}" '
            f'from "{player.name}"' if player else ''
        )

        if not beatmapset.osz_filesize:
            utils.update_osz_filesize(
                beatmapset.id,
                beatmapset.has_video
            )

        return utils.online_beatmap(beatmapset)
