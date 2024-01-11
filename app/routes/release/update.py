
from app.common.helpers import clients
from fastapi import APIRouter, Query

import config
import app

router = APIRouter()

@router.get('/update.php')
def check_for_updates(
    filename: str = Query(..., alias='f'),
    checksum: str = Query(..., alias='h'),
    ticks: int = Query(..., alias='t')
):
    if config.DISABLE_CLIENT_VERIFICATION:
        return "0"

    if not (hashes := clients.get_client_hashes_by_filename(filename)):
        return "0"

    if checksum in hashes:
        return "0"

    # Patch filename structure: <filename>_<old_checksum>_<new_checksum>.patch
    patches = [
        file.removesuffix('.patch')
        for file in app.session.storage.list('release')
        if file.endswith('.patch')
    ]

    for patch in patches:
        filename, old_checksum, new_checksum = patch.split('_')

        if old_checksum != checksum:
            continue

        # Patch file was found
        return "1"

    return "0"

@router.get('/update')
def get_files(
    ticks: int = Query(..., alias='t')
):
    # Respone format:
    # <server_filename> <file_checksum> <description> <file_action> <old_checksum>\n (for each file)
    # File action can be: "del", "noup", "zip" or "diff"
    # "del" - delete file
    # "noup" - only download file if it doesn't exist
    # "zip" - download file and unzip it
    # "diff" - download file and patch it
    # "extra" - was used in osume, inside the "extras" tab (unused)

    noup_files = (
        'Microsoft.Xna.Framework.dll',
        'Microsoft.Ink.dll',
        'd3dx9_31.dll',
        'bass_fx.dll',
        'bass.dll',
        'avutil-49.dll',
        'avformat-52.dll',
        'avcodec-51.dll'
    )

    release_files = app.session.storage.get_file_hashes('release').items()
    response = []

    for file, hash in release_files:
        if file in noup_files:
            response.append(f'{file} {hash} "" noup {hash}')
            continue

        if file.endswith('.patch'):
            filename, old_checksum, new_checksum = file.split('_')
            response.append(f'{filename} {new_checksum} "" diff {old_checksum}')
            continue

        if file.endswith('.zip'):
            response.append(f'{filename} {hash} "" zip {hash}')
            continue

    return '\n'.join(response)

@router.get('/patches.php')
def patches():
    return '\n'.join([
        file for file in app.session.storage.list('release')
        if file.endswith('.patch')
    ])
