
from fastapi import HTTPException, APIRouter, Request, Query
from app.common.database.repositories import users
from app.common.constants import regexes
from app.common.helpers import location
from datetime import datetime

import bcrypt
import config
import utils
import app

router = APIRouter()

@router.get('/bancho_connect.php')
def connect(
    request: Request,
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    version: str = Query(..., alias='v')
):
    if not (match := regexes.OSU_VERSION.match(version)):
        raise HTTPException(400)

    if not (player := users.fetch_by_name(username)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    users.update(player.id, {'latest_activity': datetime.now()})

    app.session.logger.info(
        f'Player "{player.name}" with version "{version}" is about to connect to bancho.'
    )

    date = int(match.group('date'))

    if (date > 20130815):
        # Client is connecting from an http client
        ip_address = utils.resolve_ip_address(request)
        geo = location.fetch_geolocation(ip_address)
        return geo.country_code.lower()

    if not config.BANCHO_IP:
        return

    return config.BANCHO_IP
