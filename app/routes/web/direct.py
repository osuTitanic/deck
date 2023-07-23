
from fastapi import APIRouter, Response, HTTPException, Query
from typing import Optional

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
    # TODO
    return Response('-1\nNot implemented')

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
    if not (player := app.session.database.user_by_name(username)):
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
        beatmapset = app.session.database.beatmap_by_id(beatmap_id).beatmapset

    if checksum:
        beatmapset = app.session.database.beatmap_by_checksum(checksum).beatmapset

    if set_id:
        beatmapset = app.session.database.set_by_id(set_id)

    if not beatmapset:
        raise HTTPException(404)

    if not beatmapset.osz_filesize:
        utils.update_osz_filesize(
            beatmapset.id, 
            beatmapset.has_video
        )

    return utils.online_beatmap(beatmapset)

