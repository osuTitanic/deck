
from fastapi import APIRouter

from . import rate

router = APIRouter()
router.include_router(rate.router)
