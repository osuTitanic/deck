
from fastapi.responses import PlainTextResponse
from fastapi import APIRouter

from . import release
from . import rating
from . import static
from . import web

import config

router = APIRouter(default_response_class=PlainTextResponse)
router.include_router(release.router, prefix='/release')
router.include_router(rating.router, prefix='/rating')
router.include_router(web.router, prefix='/web')
router.include_router(static.router)

@router.get('/')
def index():
    return (
        f'deck-{config.VERSION} '
        f'{"(Debug)" if config.DEBUG else ""}'
    )
