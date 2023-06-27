
from fastapi.responses import PlainTextResponse
from fastapi import APIRouter

from . import avatar
from . import web
from . import ss

import config

router = APIRouter(default_response_class=PlainTextResponse)
router.include_router(avatar.router, prefix='/a')
router.include_router(web.router, prefix='/web')
router.include_router(ss.router, prefix='/ss')

@router.get('/')
def index():
    return PlainTextResponse(f'deck-{config.VERSION}')
