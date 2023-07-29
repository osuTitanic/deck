
from fastapi import (
    HTTPException,
    APIRouter,
    Response
)

import app

router = APIRouter()

@router.get('/')
def default_avatar():
    if not (image := app.session.storage.get_avatar('unknown')):
        raise HTTPException(500, 'Default avatar not found')
    
    return Response(image)

@router.get('/{filename}')
def avatar(filename: str):
    # Workaround for older clients
    user_id = int(
        filename.replace('_000.png', '') \
                .replace('_000.jpg', '')
    )

    if not (image := app.session.storage.get_avatar(user_id)):
        return default_avatar()

    return Response(image)

# TODO: Move to seperate server
