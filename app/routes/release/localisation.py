
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Request
)

import app

router = APIRouter()

@router.get('/Localisation/{filename}')
def localisation(filename: str, request: Request):
    args = list(request.query_params.keys())
    version = f'?{args[0]}' if args else ''

    response = app.session.requests.get(f'https://m1.ppy.sh/release/Localisation/{filename}{version}')

    if not response.ok:
        raise HTTPException(response.status_code)

    return response.content

@router.get('/{language}/{filename}')
def get_legacy_localisation(
    language: str,
    filename: str
) -> bytes:
    if not filename.endswith('.dll'):
        raise HTTPException(404)

    if not (release_file := app.session.storage.get_release_file(f'{language}/{filename}')):
        raise HTTPException(404)

    return Response(
        release_file,
        media_type='application/octet-stream'
    )
