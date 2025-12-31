
from fastapi import HTTPException, APIRouter, Response, Query
from fastapi.responses import StreamingResponse
from app.common.database import releases

import hashlib
import app

router = APIRouter()

@router.get('/{filename}')
def get_file(
    filename: str,
    checksum: str | None = Query(None, alias='v')
) -> bytes:
    if not filename.startswith(('f_', 'p_')):
        # File is stored in "release" folder/bucket
        return get_extra_file(filename)

    return get_release_file(filename)

def get_extra_file(filename: str) -> StreamingResponse:
    if not (release_file := app.session.storage.get_release_file_iterator(filename)):
        raise HTTPException(404)

    return StreamingResponse(
        release_file,
        media_type='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(app.session.storage.get_release_file_size(filename) or 0)
        }
    )

def get_release_file(filename: str) -> StreamingResponse:
    file_type, checksum = filename.split('_', 1)
    is_patch = file_type == 'p'

    resolver = (
        releases.fetch_official_file_by_full if not is_patch else
        releases.fetch_official_file_by_patch
    )

    if not (release_file := resolver(filename)):
        raise HTTPException(404)

    target_url = release_file.url_patch if is_patch else release_file.url_full
    response = app.session.requests.get(target_url, allow_redirects=True, timeout=10)

    if not response.ok:
        raise HTTPException(response.status_code)

    headers = {
        'Content-Length': response.headers.get('Content-Length', '0'),
        'Content-Disposition': f'attachment; filename="{release_file.filename}"',
        'Last-Modified': release_file.timestamp.strftime('%a, %d %b %Y %H:%M:%S GMT')
    }

    if is_patch:
        headers['Content-Disposition'] = f'attachment; filename="{filename}"'

    return StreamingResponse(
        response.iter_content(chunk_size=8192),
        media_type='application/octet-stream',
        headers=headers
    )
