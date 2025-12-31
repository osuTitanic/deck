
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
    if response := get_release_file(checksum):
        # File was found in official release files
        return response

    if response := get_patch_file(filename):
        # File is an official patch file
        return response

    if response := get_extra_file(filename):
        # File is part of osume extra content
        return response

    raise HTTPException(404)

def get_extra_file(filename: str) -> StreamingResponse | None:
    if not (release_file := app.session.storage.get_release_file_iterator(filename)):
        return

    return StreamingResponse(
        release_file,
        media_type='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(app.session.storage.get_release_file_size(filename) or 0)
        }
    )

def get_patch_file(filename: str) -> StreamingResponse | None:
    if not (release_file := releases.fetch_official_file_by_patch(filename)):
        return
    
    response = app.session.requests.get(
        release_file.url_patch,
        allow_redirects=True,
        stream=True,
        timeout=10
    )

    if not response.ok:
        return

    headers = {
        'Content-Length': response.headers.get('Content-Length', '0'),
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Last-Modified': release_file.timestamp.strftime('%a, %d %b %Y %H:%M:%S GMT')
    }

    return StreamingResponse(
        response.iter_content(chunk_size=8192),
        media_type='application/octet-stream',
        headers=headers
    )

def get_release_file(checksum: str | None) -> StreamingResponse | None:
    if not checksum:
        return

    if not (release_file := releases.fetch_official_file_by_checksum(checksum)):
        return

    response = app.session.requests.get(
        release_file.url_full,
        allow_redirects=True,
        stream=True,
        timeout=10
    )

    if not response.ok:
        return

    headers = {
        'Content-Length': response.headers.get('Content-Length', '0'),
        'Content-Disposition': f'attachment; filename="{release_file.filename}"',
        'Last-Modified': release_file.timestamp.strftime('%a, %d %b %Y %H:%M:%S GMT')
    }

    return StreamingResponse(
        response.iter_content(chunk_size=8192),
        media_type='application/octet-stream',
        headers=headers
    )
