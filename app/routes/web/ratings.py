
from fastapi import APIRouter, Response, Query
from typing import Optional

router = APIRouter()

@router.get('/osu-rate.php')
def ratings(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    beatmap_md5: str = Query(..., alias='c'),
    rating: Optional[int] = Query(None, alias='v')
):
    # TODO
    return Response('not implemented')
