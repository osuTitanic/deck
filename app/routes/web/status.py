
from app.common.database import beatmaps
from sqlalchemy.orm import Session
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Depends,
    Query
)

import app

router = APIRouter()

@router.get('/osu-getstatus.php')
def get_beatmaps(
    session: Session = Depends(app.session.database.yield_session),
    checksums: str = Query(..., alias='c')
) -> Response:
    # Check amount of requests
    if len(checksums := checksums.split(',')) > 60:
        raise HTTPException(400)

    # Check md5 size
    if any([len(checksum) != 32 for checksum in checksums if checksum]):
        raise HTTPException(400)

    app.session.logger.info(f"Got beatmap status request for {len(checksums)} beatmaps.")

    response = []

    for checksum in checksums:
        if not (beatmap := beatmaps.fetch_by_checksum(checksum, session)):
            continue

        status = 1 if beatmap.status > 0 else 0

        response.append(','.join([
            str(checksum),
            str(status),
            str(beatmap.id),
            str(beatmap.set_id),
            str(beatmap.beatmapset.topic_id or "")
        ]))

    return Response('\n'.join(response))
