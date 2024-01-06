
from fastapi import HTTPException, APIRouter, Request, Query
from app.common.database.repositories import users
from app.common.helpers import location, ip
from app.common.constants import regexes
from datetime import datetime

import bcrypt
import config
import app

router = APIRouter()

def resolve_country(request: Request) -> str:
    if country_code := request.headers.get('CF-IPCountry'):
        return country_code.lower()

    ip_address = ip.resolve_ip_address_fastapi(request)
    geo = location.fetch_geolocation(ip_address)
    return geo.country_code.lower()

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

    if date <= 20130815:
        return config.BANCHO_IP or ""

    return resolve_country(request)
