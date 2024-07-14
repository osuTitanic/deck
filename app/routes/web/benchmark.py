
from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Depends,
    Form
)

from app.common.cache import status
from app.common.database.repositories import (
    benchmarks,
    users
)

router = APIRouter()

import bcrypt
import app

def calculate_grade(smoothness: float) -> str:
    if smoothness == 100: return 'SS'
    elif smoothness > 95: return 'S'
    elif smoothness > 90: return 'A'
    elif smoothness > 80: return 'B'
    elif smoothness > 70: return 'C'
    else: return 'D'

@router.post('/osu-benchmark.php')
def benchmark(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Form(..., alias='u'),
    password: str = Form(..., alias='p'),
    smoothness: float = Form(..., alias='s', ge=0, le=100),
    framerate: int = Form(..., alias='f', le=1_000_000),
    raw_score: int = Form(..., alias='r', le=1_000_000_000),
    client: str = Form(..., alias='c')
):
    if not (player := users.fetch_by_name(username, session)):
        app.session.logger.warning(f'Failed to submit score: Invalid User')
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        app.session.logger.warning(f'Failed to submit score: Invalid Password')
        raise HTTPException(401)

    if not status.exists(player.id):
        app.session.logger.warning(f'Failed to submit benchmark: Not connected to bancho')
        raise HTTPException(401)
    
    if not player.activated:
        app.session.logger.warning(f'Failed to submit benchmark: Not activated')
        raise HTTPException(401)

    if player.restricted:
        app.session.logger.warning(f'Failed to submit benchmark: Restricted')
        raise HTTPException(401)

    users.update(player.id, {'latest_activity': datetime.now()}, session)

    benchmark = benchmarks.create(
        user_id=player.id,
        smoothness=smoothness,
        framerate=framerate,
        score=raw_score,
        grade=calculate_grade(smoothness),
        client=client
    )

    return Response(str(benchmark.id))