
from app.common.database import screenshots
from fastapi import (
    HTTPException,
    APIRouter,
    Response
)

import utils
import app

router = APIRouter()

@router.get('/')
def index():
    raise HTTPException(404)

@router.get('/{id}')
def get_screenshot(id: int):
    if not (ss := screenshots.fetch_by_id(id)):
        raise HTTPException(404)

    if ss.hidden:
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
        headers={'Content-Length': str(len(image))}
    )
