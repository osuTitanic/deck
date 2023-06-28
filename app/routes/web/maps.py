
from fastapi import (
    HTTPException,
    APIRouter
)

import app

router = APIRouter()

@router.get('/maps/')
def index():
    raise HTTPException(404)

@router.get('/maps/{filename}')
def get_map(filename: str):
    if not (beatmap := app.session.database.beatmap_by_file(filename)):
        raise HTTPException(404)

    if not (file := app.session.storage.get_beatmap(beatmap.id)):
        raise HTTPException(404)

    return file
