
from fastapi import HTTPException, APIRouter, Response, Query, Depends
from fastapi.responses import StreamingResponse

from app.routes.web.beatmaps import error_response
from app.common.database import beatmapsets, users
from app.common.helpers.replays import get_ticks
from sqlalchemy.orm import Session
from urllib.parse import quote
from osz2 import Osz2Package
from app import utils

import hashlib
import config
import app

router = APIRouter()

@router.get("/osu-gethashes.php")
def get_osz2_hashes(
    session: Session = Depends(app.session.database.yield_session),
    set_id: int = Query(..., alias="s")
) -> str:
    if not (beatmapset := beatmapsets.fetch_one(set_id, session)):
        return "0"

    return "|".join(
        "1",
        beatmapset.body_hash.upper(),
        beatmapset.meta_hash.upper()
    )

@router.get("/osu-osz2-getfileinfo.php")
def get_osz2_file_info(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias="u"),
    password: str = Query(..., alias="h"),
    set_id: int = Query(..., alias="s")
) -> Response:
    player = users.fetch_by_name(username, session=session)

    if not player:
        app.session.logger.info(f"Failed to authenticate user '{username}'")
        return error_response(5, 'Authentication failed. Please check your login credentials.')

    if not app.utils.check_password(password, player.bcrypt):
        app.session.logger.info(f"Failed to authenticate user '{username}'")
        return error_response(5, 'Authentication failed. Please check your login credentials.')

    if not (osz2 := app.session.storage.get_osz2_internal(set_id)):
        app.session.logger.warning(f"Could not find osz2 package for beatmapset: '{set_id}'")
        return error_response(5)

    try:
        package = Osz2Package.from_bytes(osz2)
    except Exception as e:
        app.session.logger.warning(f"Failed to read osz2 package: {e}")
        return error_response(5)

    info_strings = [
        f"{file.filename}:{file.offset}:{file.size}:{file.hash.hex().upper()}:"
        f"{get_ticks(file.date_created)}:{get_ticks(file.date_modified)}"
        for file in package.files
    ]
    return "|".join(info_strings) + f"\n{package.data_offset}"

@router.get("/osu-osz2-getrawheader.php")
def get_osz2_header(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias="u"),
    password: str = Query(..., alias="h"),
    set_id: int = Query(..., alias="s")
) -> Response:
    player = users.fetch_by_name(username, session=session)

    if not player:
        app.session.logger.info(f"Failed to authenticate user '{username}'")
        return error_response(5, 'Authentication failed. Please check your login credentials.')

    if not app.utils.check_password(password, player.bcrypt):
        app.session.logger.info(f"Failed to authenticate user '{username}'")
        return error_response(5, 'Authentication failed. Please check your login credentials.')

    if not (osz2 := app.session.storage.get_osz2_internal(set_id)):
        app.session.logger.warning(f"Could not find osz2 package for beatmapset: '{set_id}'")
        return error_response(5)

    try:
        package = Osz2Package.from_bytes(osz2)
    except Exception as e:
        app.logger.warning(f"Failed to read osz2 package: {e}")
        return error_response(5)

    return Response(osz2[0 : package.data_offset])

@router.get("osu-osz2-getfilecontents.php")
def get_osz2_file_contents(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias="u"),
    password: str = Query(..., alias="h"),
    set_id: int = Query(..., alias="s"),
    filename: str = Query(..., alias="f")
) -> Response:
    player = users.fetch_by_name(username, session=session)

    if not player:
        return error_response(5, 'Authentication failed. Please check your login credentials.')

    if not app.utils.check_password(password, player.bcrypt):
        return error_response(5, 'Authentication failed. Please check your login credentials.')

    if not (osz2 := app.session.storage.get_osz2_internal(set_id)):
        return error_response(5)

    try:
        package = Osz2Package.from_bytes(osz2)
    except Exception as e:
        app.logger.warning(f"Failed to read osz2 package: {e}")
        return error_response(5)

    if not (file := package.find_file_by_name(filename)):
        return error_response(5)

    return Response(file.content)

@router.get("/osu-magnet.php")
def get_osu_magnet(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias="u"),
    password: str = Query(..., alias="h"),
    set_id: int = Query(..., alias="s"),
    no_video: int = Query(0, alias="v")
) -> str:
    player = users.fetch_by_name(username, session=session)

    if not player:
        raise HTTPException(401)

    if not app.utils.check_password(password, player.bcrypt):
        raise HTTPException(401)

    if not (beatmapset := beatmapsets.fetch_one(set_id, session)):
        raise HTTPException(404)

    if not beatmapset.available:
        raise HTTPException(451)

    if not beatmapset.info_hash:
        raise HTTPException(404)

    # Construct display name for the torrent
    display_name = utils.sanitize_filename(
        f"{beatmapset.artist} - {beatmapset.title}.osz2"
    )

    # Build magnet link
    magnet_parts = [
        f"xt=urn:sha1:{hashlib.sha1(beatmapset.osz2_hashes.encode()).hexdigest()}",
        f"dn={quote(display_name)}",
        f"tr={quote(config.TRACKER_BASEURL)}",
        f"x.pe={quote(f'{config.OSU_BASEURL}/web/osz2-download.php?s={set_id}&v={no_video}')}"
    ]
    return "magnet:?" + "&".join(magnet_parts)

@router.get("/osz2-download.php")
def download_osz2(
    session: Session = Depends(app.session.database.yield_session),
    set_id: int = Query(..., alias="s")
) -> Response:
    if not (beatmapset := beatmapsets.fetch_one(set_id, session)):
        raise HTTPException(404)

    if not beatmapset.available:
        raise HTTPException(451)

    if not (osz2 := app.session.storage.get_osz2_iterable(set_id)):
        raise HTTPException(404)

    osz2_filename = utils.sanitize_filename(
        f"{set_id} {beatmapset.artist} - {beatmapset.title}.osz2"
    )

    return StreamingResponse(
        content=osz2,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{osz2_filename}"',
            "Last-Modified": beatmapset.last_update.strftime('%a, %d %b %Y %H:%M:%S GMT')
        }
    )
