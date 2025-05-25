
from typing import Optional
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Request,
    Query
)

import app.utils as utils
import app

router = APIRouter()

@router.get('/a/')
def default_avatar():
    if not (image := app.session.storage.get_avatar('unknown')):
        raise HTTPException(500, 'Default avatar not found')

    return Response(image, media_type='image/png')

@router.get('/a/{filename}')
def avatar(filename: str, size: Optional[int] = Query(128, alias='s')):
    # Workaround for older clients
    user_id = int(
        filename.replace('_000.png', '').replace('_000.jpg', '')
    )

    if (image := app.session.redis.get(f'avatar:{user_id}:{size}')):
        return Response(
            image,
            media_type='image/png',
            headers={'Cache-Control': 'stale-while-revalidate, max-age=10'}
        )

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
        media_type='image/png',
        headers={'Cache-Control': 'stale-while-revalidate, max-age=10'}
    )

@router.get('/forum/download.php')
def legacy_avatar(request: Request):
    args = request.query_params

    if not (filename := args.get('avatar')):
        return default_avatar()

    return avatar(str(filename), size=128)
