
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

@router.get('/{user_id}')
def avatar(user_id: int):
    if not (image := app.session.storage.get_avatar(user_id)):
        return default_avatar()

    return Response(image)
