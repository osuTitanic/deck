
from fastapi import (
    HTTPException,
    UploadFile,
    APIRouter, 
    Response,
    Query, 
    File
)

import bcrypt
import app

router = APIRouter()

@router.post('/osu-screenshot.php')
async def screenshot(
    screenshot: UploadFile = File(..., alias='ss'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p')
):
    if not (player := app.session.database.user_by_name(username)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    id = app.session.database.submit_screenshot(player.id, False)

    app.session.storage.upload_screenshot(id, await screenshot.read())

    return Response(str(id))

@router.get('/osu-ss.php')
async def monitor(
    screenshot: UploadFile = File(..., alias='ss'),
    user_id: int = Query(..., alias='u'),
    password: str = Query(..., alias='h')
):
    # This endpoint will be called, when the client receives a
    # monitor packet from bancho

    if not (player := app.session.database.user_by_id(user_id)):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    id = app.session.database.submit_screenshot(player.id, True)

    app.session.storage.upload_screenshot(id, await screenshot.read())

    return Response('ok')
