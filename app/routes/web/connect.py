
from app.common.database.repositories import users
from app.common.helpers import location, ip
from app.common.constants import regexes
from fastapi import APIRouter, Request, Query
from datetime import datetime

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
    retry: bool = Query(False),
    version: str = Query(..., alias='v'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    framework: str = Query("dotnet30", alias="fx"),
    failure: str | None = Query(None, alias='fail')
) -> str:
    if not (match := regexes.OSU_VERSION.match(version)):
        return "XX"

    app.session.logger.info(
        f'Player "{username}" with version "{version}" is about to connect to bancho.'
    )

    # NOTE: It's possible to respond with "420" here to
    #       indicate that the server is busy. osu! will
    #       proceed to show: "Server is busy, please wait..."

    date = int(match.group('date'))

    if date <= 20130815:
        return config.BANCHO_IP or ""

    return resolve_country(request)
