
from fastapi import APIRouter

from . import error

router = APIRouter()
router.include_router(error.router)
