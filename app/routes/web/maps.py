
from fastapi import HTTPException, APIRouter, Response
from app.common.database.objects import DBBeatmap
from app.common.database import beatmaps
from urllib.parse import quote

import app

router = APIRouter()

@router.get('/maps/{query}')
def beatmap_file(query: str) -> Response:
    app.session.logger.info(f'Got map request for: "{query}".')

    if not (beatmap := resolve_beatmap(query)):
        raise HTTPException(404)

    if not (file := app.session.storage.get_beatmap(beatmap.id)):
        raise HTTPException(404)

    return Response(
        content=file,
        media_type='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{quote(beatmap.filename)}"',
            'Last-Modified': beatmap.last_update.strftime('%a, %d %b %Y %H:%M:%S GMT')
        }
    )

def resolve_beatmap(query: str) -> DBBeatmap | None:
    query = query.strip()

    if query.isdigit():
        return beatmaps.fetch_by_id(int(query))

    if query.endswith('.osu'):
        return beatmaps.fetch_by_file(query)

    return beatmaps.fetch_by_checksum(query)
