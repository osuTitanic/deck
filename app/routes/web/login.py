
from app.common.database.repositories import users

from datetime import datetime
from fastapi import (
    APIRouter,
    Query
)

import bcrypt
import app

router = APIRouter()

@router.get('/osu-login.php')
def legacy_login(
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

    # TODO: Open session for irc connection

    return "1"
