
from app.common.objects import DBStats

from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Query
)

router = APIRouter()

import bcrypt
import app

@router.get('/osu-getreplay.php')
def get_replay(
    score_id: int = Query(..., alias='c'),
    mode: int = Query(..., alias='m'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h')
):
    if not (player := app.session.database.user_by_name(username)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    if not app.session.cache.user_exists(player.id):
        raise HTTPException(401)

    app.session.database.update_latest_activity(player.id)

    if not (score := app.session.database.score(score_id)):
        raise HTTPException(404)

    if player.id != score.user.id:
        app.session.database.update_replay_views(player.id, mode)

    if score.status <= 0:
        # Score is hidden
        raise HTTPException(403)

    if not (replay := app.session.storage.get_replay(score_id)):
        raise HTTPException(404)

    return Response(replay)
