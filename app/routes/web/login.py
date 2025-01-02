
from app.common.database import users
from fastapi import APIRouter, Query
from datetime import datetime

import utils
import app

router = APIRouter()

@router.get('/osu-login.php')
def legacy_login(
    username: str = Query(...),
    password: str = Query(...)
) -> str:
    with app.session.database.managed_session() as session:
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
