
from app.common.database.repositories import users
from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session
from datetime import datetime

import utils
import app

router = APIRouter()

@router.get('/osu-login.php')
def legacy_login(
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

    app.session.logger.info(
        f'Player "{player.name}" is about to connect to irc.'
    )

    return "1"
