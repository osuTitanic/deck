
from fastapi import APIRouter, Response, Query
from typing import Optional

router = APIRouter()

@router.get('/osu-osz2-getscores.php')
def get_scores(
    ranking_type: Optional[int] = Query(..., alias='v'),
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    get_scores: int = Query(..., alias='s'),
    username: str = Query(..., alias='us'),
    password: str = Query(..., alias='ha'),
    osz_hash: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='i'),
    mode: int = Query(..., alias='m'),
    mods: Optional[int] = Query(...)
):
    # TODO
    return Response('-1|false')
