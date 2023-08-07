
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

    if not (beatmap_set := beatmapsets.fetch_one(set_id)):
        raise HTTPException(404)

    favourites.create(player.id, beatmap_set.id)

    app.session.logger.info(f'<{player.name} ({player.id})> -> Added favourite on set: {beatmap_set.id}')

    return Response('ok')

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
