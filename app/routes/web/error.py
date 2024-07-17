
from __future__ import annotations

from app.common.database import users
from app.common import officer

from sqlalchemy.orm import Session
from typing import Dict
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Depends,
    Form
)

router = APIRouter()

import bcrypt
import json
import app

def parse_osu_config(config: str) -> Dict[str, str]:
    return {
        k.strip():v.strip()
        for (k, v) in [
            line.split('=', 1) for line in config.splitlines()
            if '=' in line and not line.startswith('#')
        ]
    }

@router.post('/osu-error.php')
def osu_error(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Form(..., alias='u'),
    user_id: int | None = Form(None, alias='i'),
    language: str = Form(..., alias='culture'),
    mode: str = Form(..., alias='gamemode'),
    time: int = Form(..., alias='gametime'),
    beatmap_id: int | None = Form(None, alias='b'),
    beatmap_md5: str | None = Form(None, alias='bc'),
    audiotime: int = Form(...),
    exception: str = Form(...),
    stacktrace: str = Form(...),
    feedback: str | None = Form(None),
    iltrace: str | None = Form(None),
    exehash: str | None = Form(None),
    version: str = Form(...),
    config: str = Form(...)
):
    # Parse config to get password
    config = parse_osu_config(config)

    if not (user := users.fetch_by_id(user_id, session=session)):
        raise HTTPException(401)

    if not bcrypt.checkpw(config.get('Password', '').encode(), user.bcrypt.encode()):
        raise HTTPException(401)

    if user.restricted or not user.activated:
        raise HTTPException(401)

    flagged_skins = [
        'taikomania',
        'duda skin',
        'arpia97'
    ]

    skin_name = config.get('Skin', '').lower()

    # Check if player is using a flagged skin
    if any(name in skin_name for name in flagged_skins):
        officer.call(
            f'"{user.name}" is using a flagged skin: "{config["Skin"]}"',
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

    app.session.events.submit(
        'osu_error',
        user_id,
        error_dict
    )

    return Response(status_code=200)
