
from fastapi import (
    HTTPException,
    APIRouter,
    Request
)

import app

router = APIRouter()

@router.get('/Localisation/{filename}')
def localization(filename: str, request: Request):
    args = list(request.query_params.keys())
    version = f'?{args[0]}' if args else ''

    response = app.session.requests.get(f'https://m1.ppy.sh/release/Localisation/{filename}{version}')

    if not response.ok:
        raise HTTPException(response.status_code)

    return response.content
