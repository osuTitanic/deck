
from fastapi.responses import RedirectResponse
from fastapi import APIRouter, Response, Query
from datetime import datetime
from typing import Optional

from app.common.cache import status
from app.common.database.repositories import (
    beatmaps,
    ratings,
    users
)

router = APIRouter()

import bcrypt
import app

@router.get('/osu-rate.php')
def rate(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    beatmap_md5: str = Query(..., alias='c'),
    rating: Optional[int] = Query(None, alias='v')
):
    if not (player := users.fetch_by_name(username)):
        return Response('auth fail')
    
    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        return Response('auth fail')

    if not status.exists(player.id):
        return Response('auth fail')

    users.update(player.id, {'latest_activity': datetime.now()})
    
    if not (beatmap := beatmaps.fetch_by_checksum(beatmap_md5)):
        return Response('no exist')

    if beatmap.status <= 0:
        return Response('not ranked')

    if beatmap.beatmapset.creator == player.name:
        # This is pretty useless...
        return Response('owner')

    previous_rating = ratings.fetch_one(beatmap.md5, player.id)
        
    if previous_rating:
        return Response(
            '\n'.join([
                'alreadyvoted',
                str(ratings.fetch_average(beatmap.md5))
            ]))
    
    if rating is None:
        return Response('ok')

    if rating < 0 or rating > 10:
        return RedirectResponse('https://pbs.twimg.com/media/Dqnn54dVYAAVuki.jpg')

    ratings.create(
        beatmap.md5,
        player.id,
        beatmap.set_id,
        rating
    )

    app.session.logger.info(
        f'<{player.name} ({player.id})> -> Submitted rating of {rating} on "{beatmap.full_name}".'
    )

    return Response(
        '\n'.join([
            'ok',
            str(ratings.fetch_average(beatmap.md5))
        ]))
