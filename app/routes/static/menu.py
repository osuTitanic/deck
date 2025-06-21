
from fastapi.responses import JSONResponse
from fastapi import APIRouter

import config
import app

router = APIRouter()

@router.get('/menu-content.json', response_class=JSONResponse)
def menu_content() -> dict:
    return {
        'images': [{
            'image': config.MENUICON_IMAGE,
            'url': config.MENUICON_URL,
            'IsCurrent': True,
            'begins': None,
            'expires': None
        }]
    }
