
from typing import Optional

from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Query
)

import utils
import app

router = APIRouter()

@router.get('/')
def default_avatar():
    if not (image := app.session.storage.get_avatar('unknown')):
        raise HTTPException(500, 'Default avatar not found')
    
    return Response(image, media_type='image/png')

@router.get('/{filename}')
def avatar(
    filename: str,
    height: Optional[int] = Query(None, alias='h'),
    width: Optional[int] = Query(None, alias='w')
):
    # Workaround for older clients
    user_id = int(
        filename.replace('_000.png', '') \
                .replace('_000.jpg', '')
    )

    if not (image := app.session.storage.get_avatar(user_id)):
        return default_avatar()

    if height is None:
        # Default height for avatars
        height = 128
    else:
        # If height/width is <= 0 it should return the default avatar size
        height = None if height is not None and height <= 0 else height
        width = None if width is not None and width <= 0 else width

    if height or width:
        image = utils.resize_image(image, width, height)

    return Response(
        image,
        media_type='image/jpeg' \
            if utils.has_jpeg_headers(memoryview(image))
            else 'image/png'
    )
