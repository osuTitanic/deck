
from fastapi import APIRouter

from . import localisation
from . import filter

router = APIRouter()
router.include_router(localisation.router)
router.include_router(filter.router)
