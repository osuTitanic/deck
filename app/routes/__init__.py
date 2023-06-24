
from fastapi.responses import Response
from fastapi import APIRouter

from . import avatar
from . import web
from . import ss

import config

router = APIRouter()
router.include_router(avatar.router, prefix='/a')
router.include_router(web.router, prefix='/web')
router.include_router(ss.router, prefix='/ss')

@router.get('/')
def index():
    return Response(f'deck-{config.VERSION}')
