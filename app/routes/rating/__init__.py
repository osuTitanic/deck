
from fastapi import APIRouter

from . import rate2

router = APIRouter()
router.include_router(rate2.router)
