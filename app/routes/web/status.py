
from app.common.database.repositories import beatmaps
from app.common.constants import LegacyStatus

from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Query
)

router = APIRouter()

@router.get('/osu-getstatus.php')
def get_beatmaps(
    checksums: str = Query(..., alias='c')
):
    # Check amount of requests
    if len(checksums := checksums.split(',')) > 35:
        raise HTTPException(404)

    # Check md5 size
    if any([len(checksum) != 32 for checksum in checksums if checksum]):
        raise HTTPException(400)

    response = []

    for checksum in checksums:
        if not (beatmap := beatmaps.fetch_by_checksum(checksum)):
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
