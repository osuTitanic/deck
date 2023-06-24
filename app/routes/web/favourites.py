
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

@router.get('/osu-addfavourite.php')
def add_favourite(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='a')
):
    # TODO
    raise HTTPException(501)

@router.get('/osu-getfavourites.php')
def get_favourites(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h')
):
    # TODO
    raise HTTPException(501)
