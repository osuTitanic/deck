
from fastapi import APIRouter

from . import beatmapsets
from . import screenshots
from . import avatars

router = APIRouter()
router.include_router(screenshots.router, prefix="/ss")
router.include_router(beatmapsets.router)
router.include_router(avatars.router)
