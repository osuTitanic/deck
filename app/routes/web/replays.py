
from app.common.cache import status
from app.common.database import DBStats
from app.common.database.repositories import (
    histories,
    scores,
    stats,
    users
)

from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Depends,
    Query
)

router = APIRouter()

import bcrypt
import app

@router.get('/osu-getreplay.php')
def get_replay(
    session: Session = Depends(app.session.database.yield_session),
    score_id: int = Query(..., alias='c'),
    mode: int = Query(0, alias='m'),
    username: str = Query(None, alias='u'),
    password: str = Query(None, alias='h')
):
    # NOTE: Old clients don't have authentication for this endpoint
    player = None

    if username:
        if not (player := users.fetch_by_name(username, session)):
            raise HTTPException(401)

        if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
            raise HTTPException(401)

        if not status.exists(player.id):
            raise HTTPException(401)

        users.update(player.id, {'latest_activity': datetime.now()}, session)

    app.session.logger.info(f'{player} requested replay for "{score_id}".')

    if not (score := scores.fetch_by_id(score_id, session)):
        app.session.logger.warning(f'Failed to get replay "{score_id}": Not found')
        raise HTTPException(404)

    if player and player.id != score.user.id:
        histories.update_replay_views(
            score.user.id,
            mode,
            session
        )
        stats.update(
            score.user.id, mode,
            {'replay_views': DBStats.replay_views + 1},
            session
        )

    if score.status <= 0:
        # Score is hidden
        app.session.logger.warning(f'Failed to get replay "{score_id}": Hidden Score')
        raise HTTPException(403)

    if not (replay := app.session.storage.get_replay(score_id)):
        app.session.logger.warning(f'Failed to get replay "{score_id}": Not found on storage')
        raise HTTPException(404)

    return Response(replay)
