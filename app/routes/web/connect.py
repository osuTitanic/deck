
from fastapi import HTTPException, APIRouter, Query
from datetime import datetime

from app.common.database.repositories import users

import bcrypt
import config
import app

router = APIRouter()

@router.get('/bancho_connect.php')
def connect(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    version: str = Query(..., alias='v')
):
    if not (player := users.fetch_by_name(username)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    users.update(player.id, {'latest_activity': datetime.now()})

    app.session.logger.info(
        f'Player "{player.name}" with version "{version}" is about to connect to bancho.'
    )

    if not config.BANCHO_IP:
        return

    return config.BANCHO_IP
