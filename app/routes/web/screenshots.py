
from fastapi import (
    UploadFile,
    APIRouter, 
    Query, 
    File
)

router = APIRouter()

@router.post('/osu-screenshot.php')
def screenshot(
    screenshot: UploadFile = File(..., alias='ss'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p')
):
    # TODO
    return

@router.get('/osu-ss.php')
def monitor(
    screenshot: UploadFile = File(..., alias='ss'),
    user_id: int = Query(..., alias='u'),
    password: str = Query(..., alias='h')
):
    # TODO
    return
