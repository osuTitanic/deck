
from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Request,
    Depends,
    Query
)

from app.common.cache import status
from app.common.database.repositories import (
    benchmarks,
    users
)

router = APIRouter()

import app
import bcrypt

def calculate_grade(smoothness: float) -> str:
    if smoothness == 100: return 'SS'
    elif smoothness > 95: return 'S'
    elif smoothness > 90: return 'A'
    elif smoothness > 80: return 'B'
    elif smoothness > 70: return 'C'
    else: return 'D'

@router.get('/osu-benchmark.php')
def benchmark(
    request: Request,
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    smoothness: float = Query(..., alias='s'),
    framerate: int = Query(..., alias='f'),
    raw_score: int = Query(..., alias='r'),
):
    if not (player := users.fetch_by_name(username, session)):
        app.session.logger.warning(f'Failed to submit score: Invalid User')
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        app.session.logger.warning(f'Failed to submit score: Invalid Password')
        raise HTTPException(401)

    if not status.exists(player.id):
        app.session.logger.warning(f'Failed to submit benchmark: Inactive')
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
        grade=calculate_grade(smoothness)
    )

    return Response(str(benchmark.id))