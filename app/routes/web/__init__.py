
from fastapi import APIRouter

from . import error
from . import title

router = APIRouter()
router.include_router(error.router)
router.include_router(title.router)
