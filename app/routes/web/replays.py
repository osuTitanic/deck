
from app.common.cache import status
from app.common.database import DBStats
from app.common.database.repositories import (
    histories,
    scores,
    stats,
    users
)

from datetime import datetime
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
    mode: int = Query(0, alias='m'),
    username: str = Query(None, alias='u'),
    password: str = Query(None, alias='h')
):
    if username:
        if not (player := users.fetch_by_name(username)):
            raise HTTPException(401)

        if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
            raise HTTPException(401)

        if not status.exists(player.id):
            raise HTTPException(401)

        users.update(player.id, {'latest_activity': datetime.now()})
    else:
        player = None

    # Old clients don't have authentication for this...

    if not (score := scores.fetch_by_id(score_id)):
        raise HTTPException(404)

    if player and player.id != score.user.id:
        histories.update_replay_views(score.user.id, mode)
        stats.update(
            score.user.id, mode,
            {'replay_views': DBStats.replay_views + 1}
        )

    if score.status <= 0:
        # Score is hidden
        raise HTTPException(403)

    if not (replay := app.session.storage.get_replay(score_id)):
        raise HTTPException(404)

    return Response(replay)
