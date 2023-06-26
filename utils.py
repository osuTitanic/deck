
from py3rijndael import RijndaelCbc, Pkcs7Padding
from datetime import datetime
from typing import Optional

from app.common.objects import DBScore

import hashlib
import config
import base64
import time
import app
import os

def download(path: str, url: str):
    if not os.path.isfile(path):
        response = app.session.requests.get(url)
        
        if not response.ok:
            app.session.logger.error(f'Failed to download file: {url}')
            return

        with open(path, 'wb') as f:
            f.write(response.content)

def setup():
    os.makedirs(config.DATA_PATH, exist_ok=True)
    os.makedirs(f'{config.DATA_PATH}/logs', exist_ok=True)

    if not config.S3_ENABLED:
        os.makedirs(f'{config.DATA_PATH}/screenshots')
        os.makedirs(f'{config.DATA_PATH}/replays')
        os.makedirs(f'{config.DATA_PATH}/avatars')
        os.makedirs(f'{config.DATA_PATH}/images')

        if not os.listdir(f'{config.DATA_PATH}/avatars'):
            app.session.logger.info('Downloading avatars...')

            download(f'{config.DATA_PATH}/avatars/unknown', 'https://github.com/lekuru-static/download/blob/main/unknown?raw=true')
            download(f'{config.DATA_PATH}/avatars/1', 'https://github.com/lekuru-static/download/blob/main/1?raw=true')

def score_string(score: DBScore, index: int) -> str:
    return '|'.join([
        str(score.id),
        str(score.user.name),
        str(score.total_score),
        str(score.max_combo),
        str(score.n50),
        str(score.n100),
        str(score.n300),
        str(score.nMiss),
        str(score.nKatu),
        str(score.nGeki),
        str(int(score.perfect)),
        str(score.mods),
        str(score.user_id),
        str(index),
        str(time.mktime(score.submitted_at.timetuple()))
    ])

def decrypt_string(b64: Optional[str], iv: bytes, key: str = config.SCORE_SUBMISSION_KEY) -> Optional[str]:
    if not b64:
        return

    rjn = RijndaelCbc(
        key=key,
        iv=iv,
        padding=Pkcs7Padding(32),
        block_size=32
    )

    return rjn.decrypt(base64.b64decode(b64)).decode()

def get_ticks(dt) -> int:
    dt = dt.replace(tzinfo=None)
    return int((dt - datetime(1, 1, 1)).total_seconds() * 10000000)

def compute_score_checksum(score: DBScore) -> str:
    return hashlib.md5(
        '{}p{}o{}o{}t{}a{}r{}e{}y{}o{}u{}{}{}'.format(
            (score.n100 + score.n300),
            score.n50,
            score.nGeki,
            score.nKatu,
            score.nMiss,
            score.beatmap.md5,
            score.max_combo,
            score.perfect,
            score.user.name,
            score.total_score,
            score.grade,
            score.mods,
            (not score.failtime) # (passed)
        ).encode()
    ).hexdigest()
