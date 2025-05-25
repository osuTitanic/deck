
from fastapi import APIRouter, Request, Query, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.common.database.repositories import users
from app.common.helpers import ip
from app import utils

import app

router = APIRouter()

@router.get('/osu-login.php')
def legacy_login(
    request: Request,
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(...),
    password: str = Query(...)
) -> str:
    if not (player := users.fetch_by_name(username, session=session)):
        return "0"

    if not utils.check_password(password, player.bcrypt):
        return "0"

    if player.restricted or not player.activated:
        return "0"

    users.update(
        player.id,
        {'latest_activity': datetime.now()},
        session=session
    )

    ip_address = ip.resolve_ip_address_fastapi(request)

    app.session.redis.setex(
        f"bancho:irc_login:{player.safe_name}",
        10, ip_address
    )

    app.session.logger.info(
        f'Player "{player.name}" is about to connect via. irc based osu!.'
    )

    return "1"
