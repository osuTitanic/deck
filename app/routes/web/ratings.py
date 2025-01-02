
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from fastapi import (
    APIRouter,
    Response,
    Depends,
    Query
)

from app.common.cache import status
from app.common.database import (
    beatmaps,
    ratings,
    users
)

router = APIRouter()

import utils
import app

@router.get('/osu-rate.php')
def rate(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    beatmap_md5: str = Query(..., alias='c'),
    rating: Optional[int] = Query(None, alias='v')
):
    if not (player := users.fetch_by_name(username, session)):
        return Response('auth fail')

    if not utils.check_password(password, player.bcrypt):
        return Response('auth fail')

    if not status.exists(player.id):
        return Response('auth fail')

    users.update(player.id, {'latest_activity': datetime.now()}, session)

    if not (beatmap := beatmaps.fetch_by_checksum(beatmap_md5, session)):
        return Response('no exist')

    if beatmap.status <= 0:
        return Response('not ranked')

    if beatmap.beatmapset.creator_id == player.id:
        return Response('owner')

    previous_rating = ratings.fetch_one(beatmap.md5, player.id, session)

    if previous_rating:
        return Response(
            '\n'.join([
                'alreadyvoted',
                str(ratings.fetch_average(beatmap.md5, session))
            ]))

    if rating is None:
        return Response('ok')

    if rating < 0 or rating > 10:
        return Response('no')

    ratings.create(
        beatmap.md5,
        player.id,
        beatmap.set_id,
        rating,
        session
    )

    app.session.logger.info(
        f'<{player.name} ({player.id})> -> Submitted rating of {rating} on "{beatmap.full_name}".'
    )

    return Response(
        '\n'.join([
            'ok',
            str(ratings.fetch_average(beatmap.md5, session))
        ]))
