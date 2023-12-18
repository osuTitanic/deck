
from app.common.database.repositories import logs, users
from app.common.cache import status

from typing import Optional
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Form
)

router = APIRouter()

import bcrypt
import utils
import json
import app

@router.post('/osu-error.php')
def osu_error(
    username: str = Form(..., alias='u'),
    user_id: Optional[int] = Form(None, alias='i'),
    language: str = Form(..., alias='culture'),
    mode: str = Form(..., alias='gamemode'),
    time: int = Form(..., alias='gametime'),
    beatmap_id: Optional[int] = Form(None, alias='b'),
    beatmap_md5: Optional[str] = Form(None, alias='bc'),
    audiotime: int = Form(...),
    exception: str = Form(...),
    stacktrace: str = Form(...),
    feedback: Optional[str] = Form(None),
    iltrace: Optional[str] = Form(None),
    exehash: Optional[str] = Form(None),
    version: str = Form(...),
    config: str = Form(...)
):
    if not status.exists(user_id):
        raise HTTPException(400)

    # Parse config to get password
    config = utils.parse_osu_config(config)

    with app.session.database.managed_session() as session:
        if not (user := users.fetch_by_id(user_id, session)):
            raise HTTPException(400)

        if not bcrypt.checkpw(config['Password'].encode(), user.bcrypt.encode()):
            raise HTTPException(400)

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

        logs.create(
            json.dumps(error_dict),
            'error',
            'osu-error',
            session
        )

        app.session.events.submit(
            'osu_error',
            user_id,
            error_dict
        )

        return Response(status_code=200)
