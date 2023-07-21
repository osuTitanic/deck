
from fastapi import (
    HTTPException,
    APIRouter,
    Response
)

import app

router = APIRouter()

@router.get('/achievements/{filename}')
def achievement_image(filename: str):
    if not (image := app.session.storage.get_achievement(filename)):
        raise HTTPException(404)

    return Response(image)
