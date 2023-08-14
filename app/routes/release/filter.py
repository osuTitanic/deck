
from fastapi import APIRouter, HTTPException

import app

router = APIRouter()

@router.get('/filter.txt')
def get_filter():
    response = app.session.requests.get('https://m1.ppy.sh/release/filter.txt')

    if not response.ok:
        raise HTTPException(response.status_code)

    return response.content
