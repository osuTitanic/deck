
from fastapi import APIRouter

from . import localisation
from . import filter
from . import update
from . import files

router = APIRouter()
router.include_router(localisation.router)
router.include_router(filter.router)
router.include_router(update.router)
router.include_router(files.router)
