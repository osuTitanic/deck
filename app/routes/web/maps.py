
from app.common.database import beatmaps
from urllib.parse import quote
from fastapi import (
    HTTPException,
    APIRouter,
    Response
)

import app

router = APIRouter()

@router.get('/maps/{filename}')
def beatmap_file(filename: str) -> Response:
    app.session.logger.info(f'Got map request for: "{filename}".')

    if not (beatmap := beatmaps.fetch_by_file(filename)):
        raise HTTPException(404)

    if not (file := app.session.storage.get_beatmap(beatmap.id)):
        raise HTTPException(404)

    return Response(
        content=file,
        media_type='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{quote(filename)}"'
        }
    )
