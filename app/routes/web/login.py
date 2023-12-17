
from app.common.database.repositories import users

from datetime import datetime
from fastapi import (
    Request,
    APIRouter,
    Query
)

import bcrypt
import utils
import app

router = APIRouter()

@router.get('/osu-login.php')
def legacy_login(
    request: Request,
    username: str = Query(...),
    password: str = Query(...)
):
    if not (player := users.fetch_by_name(username)):
        return "0"

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        return "0"

    users.update(player.id, {'latest_activity': datetime.now()})

    app.session.logger.info(
        f'Player "{player.name}" is about to connect to irc.'
    )

    # Set new ip address in cache
    app.session.redis.set(
        f'irc:{player.id}',
        utils.resolve_ip_address(request)
    )

    return "1"
