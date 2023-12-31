
from app.common.database.repositories import beatmaps

from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Query
)

import app

router = APIRouter()

@router.get('/osu-getstatus.php')
def get_beatmaps(checksums: str = Query(..., alias='c')):
    with app.session.database.managed_session() as session:
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
                "" # beatmap.topic_id
            ]))

        return Response('\n'.join(response))
