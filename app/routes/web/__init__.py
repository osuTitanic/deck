
from fastapi import APIRouter

from . import leaderboards
from . import screenshots
from . import checktweets
from . import favourites
from . import comments
from . import scoring
from . import connect
from . import replays
from . import ratings
from . import status
from . import direct
from . import error
from . import title
from . import stats
from . import login
from . import maps

router = APIRouter()
router.include_router(leaderboards.router)
router.include_router(screenshots.router)
router.include_router(checktweets.router)
router.include_router(favourites.router)
router.include_router(comments.router)
router.include_router(scoring.router)
router.include_router(connect.router)
router.include_router(ratings.router)
router.include_router(replays.router)
router.include_router(status.router)
router.include_router(direct.router)
router.include_router(error.router)
router.include_router(title.router)
router.include_router(stats.router)
router.include_router(login.router)
router.include_router(maps.router)
