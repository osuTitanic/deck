
from fastapi import APIRouter, Query

import hashlib
import app

router = APIRouter()

updates = [
    {
        'filename': 'osu!.exe',
        'description': '',
        'localfilename': 'osu!.exe',
        'checksum': '9cbe9860afbfc39030c2c34c9434a98c',
        'tests': ['extra']
    }
]

@router.get('/update.php')
def check_for_updates(
    filename: str = Query(..., alias='f'),
    checksum: str = Query(..., alias='h'),
    ticks: int = Query(..., alias='t')
):
    if not (file := app.session.storage.get_release_file(filename)):
        return "0"

    if checksum.lower() == hashlib.md5(file).hexdigest():
        return "0"

    return "1"

@router.get('/update')
def get_updates(ticks: int = Query(..., alias='time')):
    return '\n'.join([
        ' '.join([
            update['filename'],
            update['checksum'],
            update['description'].replace(' ', '-'),
            ','.join(update['tests']),
            update['localfilename'].replace('\\', '/')
        ])
        for update in updates
    ])

@router.get('/patches.php')
def patches():
    return '\n'.join(app.session.storage.list('patches'))
