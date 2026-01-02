
from app.common.database import users
from app.common import officer
from sqlalchemy.orm import Session
from typing import Dict
from fastapi import (
    APIRouter,
    Response,
    Depends,
    Form
)

import json
import app

router = APIRouter()
ignored_feedback = ('update error',)
flagged_skins = ('taikomania', 'duda skin', 'arpia97')

@router.post('/osu-error.php')
def osu_error(
    session: Session = Depends(app.session.database.yield_session),
    beatmap_md5: str | None = Form(None, alias='bc'),
    beatmap_id: int | None = Form(None, alias='b'),
    language: str = Form(..., alias='culture'),
    mode: str = Form(..., alias='gamemode'),
    time: int = Form(..., alias='gametime'),
    username: str = Form(..., alias='u'),
    user_id: int | None = Form(None, alias='i'),
    config: str = Form(..., max_length=2**13),
    iltrace: str | None = Form(None),
    exehash: str | None = Form(None),
    feedback: str = Form('unknown'),
    stacktrace: str = Form(...),
    audiotime: int = Form(...),
    exception: str = Form(...),
    version: str = Form(...)
) -> Response:
    if feedback.lower() in ignored_feedback:
        return Response(status_code=200)

    if not (user := users.fetch_by_id(user_id, session=session)):
        return Response(status_code=200)

    if user.restricted or not user.activated:
        return Response(status_code=200)

    osu_config = parse_osu_config(config)
    skin_name = osu_config.get('Skin', '').lower()

    # Check if player is using a flagged skin
    if any(name in skin_name for name in flagged_skins):
        officer.call(
            f'"{user.name}" is using a flagged skin: "{osu_config["Skin"]}"',
        )

    error_dict = {
        'user_id': user_id,
        'version': version,
        'feedback': feedback,
        'iltrace': iltrace,
        'exception': exception,
        'stacktrace': stacktrace,
        'exehash': exehash
    }
    app.session.logger.warning(
        f'Client error from "{username}":\n'
        f'{json.dumps(error_dict, indent=4)}'
    )

    return Response(status_code=200)

def parse_osu_config(config: str) -> Dict[str, str]:
    if config.count('\n') > 2**8:
        return {}

    return {
        k.strip():v.strip()
        for (k, v) in [
            line.split('=', 1) for line in config.splitlines()
            if '=' in line and not line.startswith('#')
        ]
    }
