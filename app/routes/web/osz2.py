
from fastapi import HTTPException, APIRouter, Response, Query, Depends
from app.routes.web.beatmaps import error_response
from app.common.database import beatmapsets, users
from sqlalchemy.orm import Session
from osz2 import Osz2Package

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
        beatmapset.body_hash,
        beatmapset.meta_hash
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

    info_strings = [
        f"{file.filename}:{file.offset}:{file.size}:{file.hash.hex().upper()}:"
        f"{int(file.date_created.timestamp())}:{int(file.date_modified.timestamp())}"
        for file in package.files
    ]
    return "|".join(info_strings) + "\n"

@router.get("/osu-osz2-getrawheader.php")
def get_osz2_header(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias="u"),
    password: str = Query(..., alias="h"),
    set_id: int = Query(..., alias="s")
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

    # osu! magnets are not supported yet, and probably never will be...
    raise HTTPException(501)
