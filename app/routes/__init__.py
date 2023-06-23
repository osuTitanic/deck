
from fastapi.responses import Response
from fastapi import APIRouter

import config

router = APIRouter()

@router.get('/')
def index():
    return Response(f'deck-{config.VERSION}')
