
from app.common.cache import status
from app.common.database.repositories import (
    screenshots,
    users
)

from datetime import datetime
from fastapi import (
    HTTPException,
    APIRouter, 
    Response,
    Request,
    Depends,
    Query
)

import bcrypt
import utils
import app

router = APIRouter()

async def read_screenshot(request: Request):
    form = await request.form()

    if not (screenshot := form.get('ss')):
        raise HTTPException(
            status_code=400,
            detail='File missing'
        )

    if screenshot.filename not in ('jpg', 'png', 'ss'):
        raise HTTPException(
            status_code=400,
            detail='Invalid screenshot'
        )

    return await screenshot.read()

@router.post('/osu-screenshot.php')
def screenshot(
    screenshot: bytes = Depends(read_screenshot),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p')
):
    if not (player := users.fetch_by_name(username)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    if not status.exists(player.id):
        raise HTTPException(401)

    with memoryview(screenshot) as screenshot_view:
        if len(screenshot_view) > (4 * 1024 * 1024):
            raise HTTPException(
                status_code=400,
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

        app.session.storage.upload_screenshot(id, screenshot)
        app.session.logger.info(f'{player.name} uploaded a screenshot ({id})')

    return Response(str(id))

@router.post('/osu-ss.php')
def monitor(
    screenshot: bytes = Depends(read_screenshot),
    user_id: int = Query(..., alias='u'),
    password: str = Query(..., alias='h')
):
    # This endpoint will be called, when the client receives a
    # monitor packet from bancho. This was removed because of
    # privacy reasons.

    raise HTTPException(status_code=501)
