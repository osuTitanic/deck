
from app.common.cache import status
from app.common.database.repositories import (
    screenshots,
    users
)

from sqlalchemy.orm import Session
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
        app.session.logger.warning('Failed to upload screenshot: Missing file')
        raise HTTPException(
            status_code=400,
            detail='File missing'
        )

    if screenshot.filename not in ('jpg', 'png', 'ss'):
        app.session.logger.warning('Failed to upload screenshot: Invalid filename')
        raise HTTPException(
            status_code=400,
            detail='Invalid screenshot'
        )

    return await screenshot.read()

@router.post('/osu-screenshot.php')
def screenshot(
    request: Request,
    session: Session = Depends(app.session.database.yield_session),
    screenshot: bytes = Depends(read_screenshot),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p')
):
    if not (player := users.fetch_by_name(username, session)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    if not status.exists(player.id):
        raise HTTPException(401)

    with memoryview(screenshot) as screenshot_view:
        if len(screenshot_view) > (4 * 1024 * 1024):
            app.session.logger.warning('Failed to upload screenshot: Too large')
            raise HTTPException(
                status_code=400,
                detail="Screenshot file too large"
            )

        if not utils.has_jpeg_headers(screenshot_view) \
        and not utils.has_png_headers(screenshot_view):
            app.session.logger.warning('Failed to upload screenshot: Invalid filetype')
            raise HTTPException(
                status_code=400,
                detail="Invalid file type"
            )

        users.update(player.id, {'latest_activity': datetime.now()}, session)

        id = screenshots.create(player.id, hidden=False, session=session).id

    app.session.storage.upload_screenshot(id, screenshot)
    app.session.logger.info(f'{player.name} uploaded a screenshot ({id})')

    utils.track(
        'upload_screenshot',
        user=player,
        request=request,
        properties={
            'screenshot_id': id,
            'screenshot_size': len(screenshot)
        }
    )

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
