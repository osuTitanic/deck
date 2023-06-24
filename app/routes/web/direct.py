
from fastapi import APIRouter, Response, HTTPException, Query
from typing import Optional

router = APIRouter()

@router.get('/osu-search.php')
def search(
    display_mode: int = Query(4, alias='r'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    query: str = Query(..., alias='q')
):
    # TODO
    return Response('-1\nNot implemented')

@router.get('/osu-search-set.php')
def pickup_info(
    beatmap_id: Optional[int] = Query(None, alias='b'),
    topic_id: Optional[int] = Query(None, alias='t'),
    checksum: Optional[int] = Query(None, alias='c'),
    post_id: Optional[int] = Query(None, alias='p'),
    set_id: Optional[int] = Query(None, alias='s'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
):
    # TODO
    raise HTTPException(501)
