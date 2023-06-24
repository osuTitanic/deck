
from fastapi import (
    HTTPException,
    APIRouter,
    Response
)

import app

router = APIRouter()

@router.get('/{id}')
def get_screenshot(id: int):
    if not (image := app.session.storage.get_screenshot(id)):
        raise HTTPException(404)

    return Response(image)
