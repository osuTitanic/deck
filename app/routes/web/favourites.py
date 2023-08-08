
from datetime import datetime

from app.common.database.repositories import (
    beatmapsets,
    favourites,
    users
)

from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Query
)

import bcrypt
import app

router = APIRouter()

@router.get('/osu-addfavourite.php')
def add_favourite(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='a')
):
    if not (player := users.fetch_by_name(username)):
        raise HTTPException(401)
    
    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    users.update(player.id, {'latest_activity': datetime.now()})

    count = favourites.fetch_count(player.id)

    if count > 49:
        return 'You have too many favourite maps. Please go to your profile and delete some first.'

    if favourites.fetch_one(player.id, set_id):
        return 'You have already favourited this map...'

    if not (beatmap_set := beatmapsets.fetch_one(set_id)):
        raise HTTPException(404)

    count += 1

    favourites.create(player.id, beatmap_set.id)
    app.session.logger.info(
        f'<{player.name} ({player.id})> -> Added favourite on set: {beatmap_set.id}'
    )

    return f'Added to favourites! You have a total of {count} favourite{"s" if count > 1 else ""}'

@router.get('/osu-getfavourites.php')
def get_favourites(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h')
):
    if not (player := users.fetch_by_name(username)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    users.update(player.id, {'latest_activity': datetime.now()})

    player_favourites = favourites.fetch_many(player.id)

    return '\n'.join([str(favourite.set_id) for favourite in player_favourites])
