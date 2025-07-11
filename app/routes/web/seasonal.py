
from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends
from typing import List

import config
import json
import app

router = APIRouter()

@router.get('/osu-getseasonal.php', response_class=JSONResponse)
async def seasonal_backgrounds() -> List[str]:
    return config.SEASONAL_BACKGROUNDS or []
