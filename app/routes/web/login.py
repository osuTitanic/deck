
from app.common.database.repositories import users
from app.common.helpers import ip

from datetime import datetime
from fastapi import (
    Request,
    APIRouter,
    Query
)

import bcrypt
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

    if player.restricted or not player.activated:
        return "0"

    users.update(player.id, {'latest_activity': datetime.now()})

    app.session.logger.info(
        f'Player "{player.name}" is about to connect to irc.'
    )

    # Set new ip address in cache
    app.session.redis.set(
        f'irc:{player.id}',
        ip.resolve_ip_address_fastapi(request)
    )

    return "1"
