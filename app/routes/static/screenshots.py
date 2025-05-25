
from datetime import datetime, timedelta
from app.common.database import screenshots
from fastapi.responses import RedirectResponse
from fastapi import (
    HTTPException,
    APIRouter,
    Response
)

import hashlib
import app.utils as utils
import app

router = APIRouter()

@router.get('/')
def index():
    raise HTTPException(404)

@router.get('/{id}')
def get_screenshot_redirect(id: int) -> Response:
    if not (ss := screenshots.fetch_by_id(id)):
        raise HTTPException(404)

    if ss.hidden:
        raise HTTPException(404)

    time_since_created = datetime.now() - ss.created_at

    if time_since_created > timedelta(days=7):
        raise HTTPException(404)

    date_string = ss.created_at.strftime('%Y-%m-%d %H:%M:%S')
    date_checksum = hashlib.md5(date_string.encode('utf-8')).hexdigest()

    return RedirectResponse(f'/ss/{id}/{date_checksum}', 301)

@router.get('/{id}/{checksum}')
def get_screenshot(id: int, checksum: str) -> Response:
    if not (ss := screenshots.fetch_by_id(id)):
        raise HTTPException(404)

    if ss.hidden:
        raise HTTPException(404)

    date_string = ss.created_at.strftime('%Y-%m-%d %H:%M:%S')
    date_checksum = hashlib.md5(date_string.encode('utf-8')).hexdigest()

    if checksum != date_checksum:
        raise HTTPException(404)

    if not (image := app.session.storage.get_screenshot(id)):
        raise HTTPException(404)

    file_extension = (
        'jpeg' if utils.has_jpeg_headers(image)
        else 'png'
    )

    return Response(
        image,
        media_type=f"image/{file_extension}",
        headers={
            'Date': ss.created_at.strftime('%a, %d %b %Y %H:%M:%S GMT'),
            'Content-Disposition': f'inline; filename="{id}.{file_extension}"',
            'Content-Length': f'{len(image)}',
        }
    )
