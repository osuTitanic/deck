
from fastapi.responses import Response
from fastapi import APIRouter

from . import avatar

import config

router = APIRouter()
router.include_router(avatar.router, prefix='/a')

@router.get('/')
def index():
    return Response(f'deck-{config.VERSION}')
