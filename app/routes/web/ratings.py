
from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import (
    APIRouter,
    Depends,
    Query
)

from app.common.constants import UserActivity
from app.common.helpers import activity
from app.common.cache import status
from app.common.database import (
    beatmaps,
    ratings,
    users
)

router = APIRouter()

import app

@router.get('/osu-rate.php')
def rate(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    beatmap_md5: str = Query(..., alias='c'),
    rating: int | None = Query(None, alias='v')
) -> str:
    if not (player := users.fetch_by_name(username, session)):
        return 'auth fail'

    if not app.utils.check_password(password, player.bcrypt):
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

    activity.submit(
        player.id, beatmap.mode,
        UserActivity.BeatmapRated,
        {
            'username': player.name,
            'beatmap_id': beatmap.id,
            'beatmap_name': beatmap.full_name,
            'rating': rating
        },
        is_hidden=True,
        session=session
    )

    return '\n'.join([
        'ok',
        f'{ratings.fetch_average(beatmap.md5, session):.2f}'
    ])
