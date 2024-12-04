
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
def avatar(filename: str, size: Optional[int] = Query(128, alias='s')):
    # Workaround for older clients
    user_id = int(
        filename.replace('_000.png', '').replace('_000.jpg', '')
    )

    if (image := app.session.redis.get(f'avatar:{user_id}:{size}')):
        return Response(image, media_type='image/png')

    if not (image := app.session.storage.get_avatar(user_id)):
        return default_avatar()

    allowed_sizes = (
        25,
        128,
        256
    )

    if size is not None and size in allowed_sizes:
        image = utils.resize_image(image, size)
        app.session.redis.set(f'avatar:{user_id}:{size}', image, ex=3600)

    return Response(
        image,
        media_type=(
            'image/jpeg'
            if utils.has_jpeg_headers(memoryview(image))
            else 'image/png'
        )
    )
