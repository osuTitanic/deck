
from py3rijndael import RijndaelCbc, Pkcs7Padding
from datetime import datetime
from typing import Optional

from app.common.objects import DBScore

import hashlib
import config
import base64
import json
import time
import app
import os

REQUIRED_BUCKETS = [
    'screenshots',
    'avatars',
    'replays',
    'assets',
]

ACHIEVEMENTS = [
    'unknown.png',
    'anime1.png',
    'anime2.png',
    'anime3.png',
    'anime4.png',
    'bunny.png',
    'challengeaccepted.png',
    'combo500.png',
    'combo750.png',
    'combo1000.png',
    'combo2000.png',
    'consolationprize.png',
    'dancer.png',
    'gamer1.png',
    'gamer2.png',
    'gamer3.png',
    'gamer4.png',
    'plays1.png',
    'plays2.png',
    'plays3.png',
    'plays4.png',
    'fruitod.png',
    'fruitsalad.png',
    'fruitplatter.png',
    'jack.png',
    'jackpot.png',
    'lulz1.png',
    'lulz2.png',
    'lulz3.png',
    'lulz4.png',
    'maniahits1.png',
    'maniahits2.png',
    'maniahits3.png',
    'meganekko.png',
    'high-ranker-1.png',
    'high-ranker-2.png',
    'high-ranker-3.png',
    'high-ranker-4.png',
    'improved.png',
    'nonstop.png',
    'obsessed.png',
    'quickdraw.png',
    'rhythm1.png',
    'rhythm2.png',
    'rhythm3.png',
    'rhythm4.png',
    's-ranker.png',
    'stumbler.png',
    'taiko1.png',
    'taiko2.png',
    'taiko3.png'
]

ACHIEVEMENTS_BASEURL = "https://s.ppy.sh/images/achievements/"

def download(path: str, url: str):
    if not os.path.isfile(path):
        response = app.session.requests.get(url)
        
        if not response.ok:
            app.session.logger.error(f'Failed to download file: {url}')
            return

        with open(path, 'wb') as f:
            f.write(response.content)

def download_to_s3(bucket: str, key: str, url: str):
    response = app.session.requests.get(url)

    if not response.ok:
        app.session.logger.error(f'Failed to download file to s3: {url}')
        return

    return app.session.storage.save_to_s3(response.content, key, bucket)

def setup():
    os.makedirs(f'{config.DATA_PATH}/logs', exist_ok=True)

    if not config.S3_ENABLED:
        # Create required folders if not they not already exist
        os.makedirs(f'{config.DATA_PATH}/images/achievements', exist_ok=True)
        os.makedirs(f'{config.DATA_PATH}/screenshots', exist_ok=True)
        os.makedirs(f'{config.DATA_PATH}/replays', exist_ok=True)
        os.makedirs(f'{config.DATA_PATH}/avatars', exist_ok=True)

        if not os.listdir(f'{config.DATA_PATH}/avatars'):
            app.session.logger.info('Downloading avatars...')

            download(f'{config.DATA_PATH}/avatars/unknown', 'https://github.com/lekuru-static/download/blob/main/unknown?raw=true')
            download(f'{config.DATA_PATH}/avatars/1', 'https://github.com/lekuru-static/download/blob/main/1?raw=true')

        if not os.listdir(f'{config.DATA_PATH}/images/achievements'):
            app.session.logger.info('Downloading achievements...')

            for image in ACHIEVEMENTS:
                download(
                    f'{config.DATA_PATH}/images/achievements/{image}', 
                    ACHIEVEMENTS_BASEURL + image
                )
    else:
        s3 = app.session.storage.s3

        # Create required buckets if needed
        buckets = [
            bucket['Name'] for bucket in s3.list_buckets()['Buckets']
        ]

        for bucket in REQUIRED_BUCKETS:
            if bucket in buckets:
                continue

            app.session.logger.info(f'Creating bucket: "{bucket}"')
            s3.create_bucket(Bucket=bucket)

            if bucket == 'assets':
                app.session.logger.info('Downloading achievements...')

                for image in ACHIEVEMENTS:
                    download_to_s3(
                        'assets',
                        f'images/achievements/{image}',
                        ACHIEVEMENTS_BASEURL + image
                    )

            elif bucket == 'avatars':
                app.session.logger.info('Downloading avatars...')

                download_to_s3('avatars', 'unknown', 'https://github.com/lekuru-static/download/blob/main/unknown?raw=true')
                download_to_s3('avatars', '1', 'https://github.com/lekuru-static/download/blob/main/1?raw=true')

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

def submit_to_queue(type: str, data: dict):
    app.session.cache.redis.lpush(
        'bancho:queue',
        json.dumps({'type': type, 'data': data})
    )

def has_jpeg_headers(data_view: memoryview) -> bool:
    return data_view[:4] == b"\xff\xd8\xff\xe0" and data_view[6:11] == b"JFIF\x00"

def has_png_headers(data_view: memoryview) -> bool:
    return (
        data_view[:8] == b"\x89PNG\r\n\x1a\n"
        and data_view[-8] == b"\x49END\xae\x42\x60\x82"
    )
