# NOTE: This is a custom endpoint that is not actually used by the osu! client.
#       It was added as an easter egg on modded clients, that "revives" the
#       old benchmark feature.

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

import utils
import json
import app

router = APIRouter()

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
        raise HTTPException(400, "Invalid hardware format")

    required_keys = [
        'cpu', 'cores', 'threads',
        'gpu', 'ram', 'os',
        'motherboard_manufacturer',
        'motherboard', 'renderer'
    ]

    if not all(key in hardware_dict for key in required_keys):
        raise HTTPException(400, "Missing required hardware information")

    if hardware_dict['renderer'] not in ['OpenGL', 'DirectX']:
        raise HTTPException(400, "Renderer must be 'OpenGL' or 'DirectX'")

    try:
        hardware_dict['cores'] = int(hardware_dict['cores'])
        hardware_dict['threads'] = int(hardware_dict['threads'])
    except ValueError:
        raise HTTPException(400, "Cores and threads must be integers")

    try:
        hardware_dict['ram'] = int(hardware_dict['ram'])

        if hardware_dict['ram'] <= 0:
            raise ValueError
    except ValueError:
        raise HTTPException(400, "RAM must be a positive integer (in GB)")

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

    users.update(
        player.id,
        {'latest_activity': datetime.now()},
        session=session
    )

    return Response(str(benchmark.id))
