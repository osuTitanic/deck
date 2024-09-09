import json
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

import utils
import app

def calculate_grade(smoothness: float) -> str:
    if smoothness == 100: return 'SS'
    elif smoothness > 95: return 'S'
    elif smoothness > 90: return 'A'
    elif smoothness > 80: return 'B'
    elif smoothness > 70: return 'C'
    else: return 'D'

def validate_hardware_data(hardware: str) -> dict:
    try:
        hardware_dict = json.loads(hardware)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid hardware format")

    if 'renderer' not in hardware_dict:
        raise HTTPException(status_code=400, detail="Renderer is required")

    if hardware_dict['renderer'] not in ['OpenGL', 'DirectX']:
        raise HTTPException(status_code=400, detail="Renderer must be 'OpenGL' or 'DirectX'")

    # If only 'renderer' is provided, return it
    if len(hardware_dict) == 1:
        return hardware_dict

    required_keys = ['cpu', 'cores', 'threads', 'gpu', 'ram', 'os', 'motherboard_manufacturer', 'motherboard']
    
    if not all(key in hardware_dict for key in required_keys):
        raise HTTPException(status_code=400, detail="Missing required hardware information")

    try:
        hardware_dict['cores'] = int(hardware_dict['cores'])
        hardware_dict['threads'] = int(hardware_dict['threads'])
    except ValueError:
        raise HTTPException(status_code=400, detail="Cores and threads must be integers")

    try:
        hardware_dict['ram'] = int(hardware_dict['ram'])
        if hardware_dict['ram'] <= 0:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="RAM must be a positive integer (in GB)")

    return hardware_dict

@router.post('/osu-benchmark.php')
def benchmark(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Form(..., alias='u'),
    password: str = Form(..., alias='p'),
    smoothness: float = Form(..., alias='s', ge=0, le=100),
    framerate: int = Form(..., alias='f', le=1_000_000),
    raw_score: int = Form(..., alias='r', le=1_000_000_000),
    client: str = Form(..., alias='c'),
    hardware: str = Form(..., alias='h')
):
    if not (player := users.fetch_by_name(username, session)):
        app.session.logger.warning(f'Failed to submit score: Invalid User')
        raise HTTPException(401)

    if not utils.check_password(password, player.bcrypt):
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

    hardware_dict = validate_hardware_data(hardware)

    benchmark = benchmarks.create(
        user_id=player.id,
        smoothness=smoothness,
        framerate=framerate,
        score=raw_score,
        grade=calculate_grade(smoothness),
        client=client,
        hardware=hardware_dict
    )

    users.update(player.id, {'latest_activity': datetime.now()}, session)

    return Response(str(benchmark.id))
