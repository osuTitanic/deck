
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from fastapi import (
    APIRouter,
    Depends,
    Query
)

from app.common.cache import status
from app.common.database import (
    beatmaps,
    ratings,
    users
)

import app.utils as utils
import app

router = APIRouter()

@router.get('/ingame-rate.php')
def ingame_rate(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    beatmap_md5: str = Query(..., alias='c'),
    rating: Optional[int] = Query(None, alias='v')
) -> str:
    if not (player := users.fetch_by_name(username, session)):
        return 'auth fail'

    if not utils.check_password(password, player.bcrypt):
        return 'auth fail'

    if not status.exists(player.id):
        return 'auth fail'

    users.update(player.id, {'latest_activity': datetime.now()}, session)

    if not (beatmap := beatmaps.fetch_by_checksum(beatmap_md5, session)):
        return 'no exist'

    if beatmap.status <= 0:
        return 'not ranked'

    if beatmap.beatmapset.creator_id == player.id:
        return 'owner'

    previous_rating = ratings.fetch_one(beatmap.md5, player.id, session)

    if previous_rating:
        return 'alreadyvoted'

    if rating is None:
        return 'ok'

    if rating < 0 or rating > 10:
        return 'no'

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

    return f'{ratings.fetch_average(beatmap.md5, session):.2f}'

@router.get('/ingame-rate2.php')
def ingame_rate_with_rating(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    beatmap_md5: str = Query(..., alias='c'),
    rating: Optional[int] = Query(None, alias='v')
) -> str:
    if not (player := users.fetch_by_name(username, session)):
        return 'auth fail'

    if not utils.check_password(password, player.bcrypt):
        return 'auth fail'

    if not status.exists(player.id):
        return 'auth fail'

    users.update(player.id, {'latest_activity': datetime.now()}, session)

    if not (beatmap := beatmaps.fetch_by_checksum(beatmap_md5, session)):
        return 'no exist'

    if beatmap.status <= 0:
        return 'not ranked'

    if beatmap.beatmapset.creator_id == player.id:
        return 'owner'

    previous_rating = ratings.fetch_one(beatmap.md5, player.id, session)

    if previous_rating:
        return '\n'.join([
            'alreadyvoted',
            f'{ratings.fetch_average(beatmap.md5, session):.2f}'
        ])

    if rating is None:
        return 'ok'

    if rating < 0 or rating > 10:
        return 'no'

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

    return f'{ratings.fetch_average(beatmap.md5, session):.2f}'
