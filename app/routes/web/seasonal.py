
from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends
from app.session import config
from typing import List

router = APIRouter()

@router.get('/osu-getseasonal.php', response_class=JSONResponse)
async def seasonal_backgrounds() -> List[str]:
    return config.SEASONAL_BACKGROUNDS or []
