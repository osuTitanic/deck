
from app.common.helpers import clients
from fastapi import APIRouter, Query

import app

router = APIRouter()

@router.get('/update.php')
def check_for_updates(
    filename: str = Query(..., alias='f'),
    checksum: str = Query(..., alias='h'),
    ticks: int = Query(..., alias='t')
):
    if not (hashes := clients.get_client_hashes(filename)):
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
    # TODO
    ...

@router.get('/patches.php')
def patches():
    return '\n'.join([
        file for file in app.session.storage.list('release')
        if file.endswith('.patch')
    ])
