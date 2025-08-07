
from app.common.cache import status
from app.common.helpers import activity
from app.common.constants import UserActivity
from app.common.database import DBStats, DBScore, DBUser
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

import app

router = APIRouter()

@router.get('/osu-getreplay.php')
def get_replay(
    session: Session = Depends(app.session.database.yield_session),
    username: str | None = Query(None, alias='u'),
    password: str | None = Query(None, alias='h'),
    score_id: int = Query(..., alias='c'),
    mode: int = Query(0, alias='m')
) -> Response:
    # NOTE: Legacy clients don't implement authentication for this endpoint
    player = None

    if username != None:
        if not (player := users.fetch_by_name(username, session)):
            raise HTTPException(401)

        if not app.utils.check_password(password, player.bcrypt):
            raise HTTPException(401)

        if not status.exists(player.id):
            raise HTTPException(401)

        users.update(player.id, {'latest_activity': datetime.now()}, session)
        app.session.logger.info(f'{player} -> Requested replay for "{score_id}".')

    if not (score := scores.fetch_by_id(score_id, session)):
        app.session.logger.warning(f'Failed to get replay "{score_id}": Not found')
        raise HTTPException(404)

    if score.hidden:
        app.session.logger.warning(f'Failed to get replay "{score_id}": Hidden score')
        raise HTTPException(404)

    if not (replay := app.session.storage.get_replay(score_id)):
        app.session.logger.warning(f'Failed to get replay "{score_id}": Not found on storage')
        raise HTTPException(404)

    if player is not None:
        increase_replay_views(
            player, score,
            session=session
        )

    return Response(replay)

def increase_replay_views(
    viewer: DBUser,
    score: DBScore,
    session: Session
) -> None:
    if viewer.id == score.user.id:
        # Don't increase views for the player
        # watching their own replay
        return

    cooldown = app.session.redis.get(
        f"replay_cooldown:{viewer.id}:{score.user.id}"
    )

    if cooldown is not None:
        # Cooldown is active, do not increase views
        return

    histories.update_replay_views(
        score.user.id,
        score.mode,
        session
    )
    stats.update(
        score.user.id, score.mode,
        {'replay_views': DBStats.replay_views + 1},
        session
    )
    scores.update(
        score.id,
        {'replay_views': DBScore.replay_views + 1},
        session
    )
    activity.submit(
        viewer.id, score.mode,
        UserActivity.ReplayWatched,
        {
            'username': viewer.name,
            'score_id': score.id,
            'target_id': score.user.id,
            'target_name': score.user.name,
            'beatmap_id': score.beatmap.id,
            'beatmap_name': score.beatmap.full_name,
        },
        is_hidden=True,
        session=session
    )
    app.session.redis.setex(
        f"replay_cooldown:{viewer.id}:{score.user.id}",
        time=60, value=1
    )
