
from typing import Optional
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Query
)

from . import localisation
from . import changelog
from . import filter
from . import update

import hashlib
import app

router = APIRouter()
router.include_router(localisation.router)
router.include_router(changelog.router)
router.include_router(filter.router)
router.include_router(update.router)

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
