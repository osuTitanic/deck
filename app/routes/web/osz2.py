
from fastapi import APIRouter, Response, Query, Depends
from app.routes.web.beatmaps import error_response
from app.common.database import beatmapsets, users
from sqlalchemy.orm import Session
from osz2 import Osz2Package

import app

router = APIRouter()

@router.get("/osu-gethashes.php")
def get_osz2_hashes(
    session: Session = Depends(app.session.database.yield_session),
    set_id: int = Query(..., alias="s")
) -> str:
    if not (beatmapset := beatmapsets.fetch_one(set_id, session)):
        return "0"

    return "|".join(
        "1",
        beatmapset.body_hash,
        beatmapset.meta_hash
    )
