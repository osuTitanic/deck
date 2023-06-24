
from fastapi import HTTPException, APIRouter, Form
from typing import Optional

router = APIRouter()

@router.post('/osu-comment.php')
async def get_comments(
    username: str = Form(..., alias='u'),
    password: str = Form(..., alias='p'),
    playmode: int = Form(..., alias='m'),
    replay_id: int = Form(..., alias='r'),
    beatmap_id: int = Form(..., alias='b'),
    set_id: int = Form(..., alias='s'),
    action: str = Form(..., alias='a'),
    target: Optional[str] = Form(None),
    time: Optional[int] = Form(None)
):
    # TODO
    raise HTTPException(501)
