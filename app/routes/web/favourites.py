
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
    if not (player := app.session.database.user_by_name(username)):
        raise HTTPException(401)
    
    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)
    
    if not (beatmap_set := app.session.database.set_by_id(set_id)):
        raise HTTPException(404)

    app.session.database.submit_favourite(player.id, beatmap_set.id)

    app.session.logger.info(f'<{player.name} ({player.id})> -> Added favourite on set: {beatmap_set.id}')

    return Response('ok')

@router.get('/osu-getfavourites.php')
def get_favourites(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h')
):
    if not (player := app.session.database.user_by_name(username)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    favourites = app.session.database.favourites(player.id)

    return '\n'.join([str(favourite.set_id) for favourite in favourites])
