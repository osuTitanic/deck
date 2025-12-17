
from app.common.config import config_instance as config
from app.common.helpers import location, ip
from app.common.constants import regexes
from fastapi import APIRouter, Request, Query

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
    version: str = Query("b20130815", alias='v'),
    username: str | None = Query(None, alias='u'),
    password: str | None = Query(None, alias='h'),
    framework: str = Query("dotnet30", alias="fx"),
    failure: str | None = Query(None, alias='fail')
) -> str:
    if not (match := regexes.OSU_VERSION.match(version)):
        return "XX"

    # NOTE: It's possible to respond with "420" here to
    #       indicate that the server is busy. osu! will
    #       proceed to show: "Server is busy, please wait..."

    date = int(match.group('date'))

    if date <= 20130915:
        return config.BANCHO_IP or ""

    return resolve_country(request)
