
from typing import Optional
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Query
)

import hashlib
import app

router = APIRouter()

@router.get('/{filename}')
def get_release_file(
    filename: str,
    checksum: Optional[str] = Query(None, alias='v')
) -> bytes:
    if not (release_file := app.session.storage.get_release_file(filename)):
        raise HTTPException(404)

    if checksum != hashlib.md5(release_file).hexdigest():
        raise HTTPException(404)

    return Response(release_file)
