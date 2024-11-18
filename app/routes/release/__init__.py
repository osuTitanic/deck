
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

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

@router.get('/update.php')
def legacy_osume_update_endpoint(time: Optional[int] = Query(0)):
    return ""

@router.get('/update2.php')
def legacy_update_endpoint():
    return ""

@router.get('/patches.php')
def legacy_patches_endpoint():
    return ""

@router.get('/{filename}')
def get_release_file(
    filename: str,
    checksum: Optional[str] = Query(None, alias='v')
) -> bytes:
    if not (release_file := app.session.storage.get_release_file(filename)):
        raise HTTPException(404)

    if checksum != hashlib.md5(release_file).hexdigest():
        raise HTTPException(404)

    return release_file
