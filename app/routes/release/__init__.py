
from fastapi import APIRouter

from . import localisation
from . import changelog
from . import filter
from . import update

router = APIRouter()
router.include_router(localisation.router)
router.include_router(changelog.router)
router.include_router(filter.router)
router.include_router(update.router)
