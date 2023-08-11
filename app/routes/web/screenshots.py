
from app.common.cache import status
from app.common.database.repositories import (
    screenshots,
    users
)

from datetime import datetime
from fastapi import (
    HTTPException,
    UploadFile,
    APIRouter, 
    Response,
    Query, 
    File
)

import bcrypt
import utils
import app

router = APIRouter()

@router.post('/osu-screenshot.php')
async def screenshot(
    screenshot: UploadFile = File(..., alias='ss'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p')
):
    if not (player := users.fetch_by_name(username)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    if not status.exists(player.id):
        raise HTTPException(401)

    screenshot_content = await screenshot.read()

    with memoryview(screenshot_content) as screenshot_view:
        if len(screenshot_view) > (4 * 1024 * 1024):
            raise HTTPException(
                status_code=404,
                detail="Screenshot file too large"
            )

        if not utils.has_jpeg_headers(screenshot_view) \
        and not utils.has_png_headers(screenshot_view):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type"
            )

        users.update(player.id, {'latest_activity': datetime.now()})

        id = screenshots.create(player.id, hidden=False).id

        app.session.storage.upload_screenshot(id, screenshot_content)
        app.session.logger.info(f'{player.name} uploaded a screenshot ({id})')

    return Response(str(id))

@router.post('/osu-ss.php')
async def monitor(
    screenshot: UploadFile = File(..., alias='ss'),
    user_id: int = Query(..., alias='u'),
    password: str = Query(..., alias='h')
):
    # This endpoint will be called, when the client receives a
    # monitor packet from bancho

    if not (player := users.fetch_by_id(user_id)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    screenshot_content = await screenshot.read()

    with memoryview(screenshot_content) as screenshot_view:
        if len(screenshot_view) > (4 * 1024 * 1024):
            raise HTTPException(
                status_code=404,
                detail="Screenshot file too large."
            )

        if not utils.has_jpeg_headers(screenshot_view) \
        and not utils.has_png_headers(screenshot_view):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type"
            )

        users.update(player.id, {'latest_activity': datetime.now()})

        id = screenshots.create(player.id, hidden=True).id

        app.session.storage.upload_screenshot(id, screenshot_content)
        app.session.logger.info(f'{player.name} uploaded a hidden screenshot ({id})')

    return Response('ok')
