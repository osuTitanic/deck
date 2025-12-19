
from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import (
    HTTPException,
    APIRouter,
    Depends,
    Query
)

from app.common.database import beatmapsets, favourites, users
from app.common.constants import UserActivity
from app.common.helpers import activity
from app.common.cache import status

import app

router = APIRouter()

@router.get('/osu-addfavourite.php')
def add_favourite(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='a'),
) -> str:
    if not (player := users.fetch_by_name(username, session)):
        raise HTTPException(401)

    if not app.utils.check_password(password, player.bcrypt):
        raise HTTPException(401)

    if not status.exists(player.id):
        raise HTTPException(401)

    users.update(player.id, {'latest_activity': datetime.now()}, session)

    count = favourites.fetch_count(player.id, session)

    if count > 99:
        app.session.logger.warning("Failed to add favourite: Too many favourites")
        return 'You have too many favourite maps. Please go to your profile and delete some first.'

    if not (beatmapset := beatmapsets.fetch_one(set_id, session)):
        app.session.logger.warning("Failed to add favourite: Beatmap not found")
        raise HTTPException(404)

    if not favourites.create(player.id, beatmapset.id, session):
        app.session.logger.warning("Failed to add favourite: Already favourited")
        return 'You have already favourited this map...'

    count += 1

    app.session.logger.info(
        f'<{player.name} ({player.id})> -> Added favourite on set: {beatmapset.id}'
    )

    activity.submit(
        player.id, None,
        UserActivity.BeatmapFavouriteAdded,
        {
            'username': player.name,
            'beatmapset_id': beatmapset.id,
            'beatmapset_name': beatmapset.full_name
        },
        is_hidden=True,
        session=session
    )

    return f'Added to favourites! You have a total of {count} favourite{"s" if count > 1 else ""}'

@router.get('/osu-getfavourites.php')
def get_favourites(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h')
) -> str:
    if not (player := users.fetch_by_name(username, session)):
        raise HTTPException(401)

    if not app.utils.check_password(password, player.bcrypt):
        raise HTTPException(401)

    users.update(player.id, {'latest_activity': datetime.now()}, session)

    player_favourites = favourites.fetch_many(player.id, session)

    app.session.logger.info(
        f'Got favourites request from "{username}" ({len(player_favourites)})'
    )

    return '\n'.join([str(favourite.set_id) for favourite in player_favourites])
