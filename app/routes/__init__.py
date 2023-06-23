
from fastapi.responses import Response
from fastapi import APIRouter

from . import avatar
from . import web

import config

router = APIRouter()
router.include_router(avatar.router, prefix='/a')
router.include_router(web.router, prefix='/web')

@router.get('/')
def index():
    return Response(f'deck-{config.VERSION}')
