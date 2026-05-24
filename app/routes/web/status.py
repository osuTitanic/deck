
from app.common.database import DBBeatmap, DBBeatmapset
from sqlalchemy.orm import Session, load_only, selectinload
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
    checksum_query: str = Query(..., alias='c')
) -> Response:
    # Check amount of requests
    if len(checksums := checksum_query.split(',')) > 60:
        raise HTTPException(400)

    # Check md5 size
    if any([len(checksum) != 32 for checksum in checksums if checksum]):
        raise HTTPException(400)

    app.session.logger.info(
        f"Got beatmap status request for {len(checksums)} beatmaps."
    )

    results = session.query(DBBeatmap) \
        .options(
            load_only(
                DBBeatmap.id, \
                DBBeatmap.set_id, \
                DBBeatmap.md5, \
                DBBeatmap.status \
            ),
            selectinload(DBBeatmap.beatmapset).load_only(
                DBBeatmapset.id, \
                DBBeatmapset.topic_id \
            ) \
        ) \
        .filter(DBBeatmap.md5.in_(checksums)) \
        .all()
    
    found_beatmaps = {
        beatmap.md5: beatmap
        for beatmap in results
    }
    response = []

    for checksum in checksums:
        if not (beatmap := found_beatmaps.get(checksum)):
            continue

        status = (
            1 if beatmap.is_ranked else 0
        )
        response.append(','.join([
            str(checksum),
            str(status),
            str(beatmap.id),
            str(beatmap.set_id),
            str(beatmap.beatmapset.topic_id or "")
        ]))

    return Response('\n'.join(response))
