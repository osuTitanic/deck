
from fastapi import APIRouter

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

@router.get('/update2.txt')
@router.get('/update2.php')
def update():
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
