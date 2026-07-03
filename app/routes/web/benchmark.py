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

    if not isinstance(hardware_dict, dict):
        raise HTTPException(400, "Hardware must be a JSON object")

    # Always require 'renderer' and validate its value
    if 'renderer' not in hardware_dict:
        raise HTTPException(400, "Renderer must be present")

    if not isinstance(hardware_dict['renderer'], str) or len(hardware_dict['renderer']) <= 0:
        raise HTTPException(400, "Renderer must be a valid string")

    if len(hardware_dict['renderer']) > 12:
        raise HTTPException(400, "Renderer must be less than 12 characters")

    hardware_dict['renderer'] = hardware_dict['renderer'].strip()

    optional_keys = {
        'resolution',
        'fullscreen',
        'letterboxing',
        'dotnet_version',
        'client_architecture'
    }
    full_hardware_keys = {
        'cpu', 'cores', 'threads',
        'gpu', 'ram', 'os',
        'motherboard_manufacturer',
        'motherboard'
    }

    allowed_keys = set(['renderer']) | optional_keys | full_hardware_keys
    unknown_keys = set(hardware_dict.keys()) - allowed_keys

    if unknown_keys:
        raise HTTPException(400, "Unknown hardware information")

    if (fullscreen := hardware_dict.get('fullscreen')) is not None:
        if not isinstance(fullscreen, bool):
            raise HTTPException(400, "Fullscreen must be a boolean")

    if (letterboxing := hardware_dict.get('letterboxing')) is not None:
        if not isinstance(letterboxing, bool):
            raise HTTPException(400, "Letterboxing must be a boolean")

    if (resolution := hardware_dict.get('resolution')) is not None:
        if not isinstance(resolution, str) or len(resolution) <= 0 or len(resolution) > 32:
            raise HTTPException(400, "Resolution must be a valid string")

        resolution = resolution.strip().lower()
        parts = resolution.split('x')

        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            raise HTTPException(400, "Resolution must use WIDTHxHEIGHT format")

        hardware_dict['resolution'] = resolution

    # Full hardware info is optional.
    # However, If any full hardware field is present, require the whole full hardware set.
    # e.g. if 'cpu' is present, we expect the client to also provide the rest.
    has_full_hardware = any(
        key in hardware_dict and hardware_dict[key] is not None
        for key in full_hardware_keys
    )

    if not has_full_hardware:
        return hardware_dict

    if not all(key in hardware_dict and hardware_dict[key] is not None for key in full_hardware_keys):
        raise HTTPException(400, "Missing required hardware information")

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
) -> Response:
    if not (player := users.fetch_by_name(username, session)):
        app.session.logger.warning(f'Failed to submit score: Invalid User')
        raise HTTPException(401)

    if not app.utils.check_password(password, player.bcrypt):
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
