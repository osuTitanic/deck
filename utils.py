
from py3rijndael import RijndaelCbc, Pkcs7Padding
from datetime import datetime
from typing import Optional

from app.common.objects import DBScore, DBBeatmapset

import hashlib
import config
import base64
import json
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
        os.makedirs(f'{config.DATA_PATH}/screenshots', exist_ok=True)
        os.makedirs(f'{config.DATA_PATH}/replays', exist_ok=True)
        os.makedirs(f'{config.DATA_PATH}/avatars', exist_ok=True)
        os.makedirs(f'{config.DATA_PATH}/images', exist_ok=True)

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

def submit_to_queue(type: str, data: dict):
    app.session.cache.redis.lpush(
        'bancho:queue',
        json.dumps({'type': type, 'data': data})
    )

def online_beatmap(set: DBBeatmapset) -> str:
    ratings = [r.rating for r in set.ratings]
    avg_rating = (sum(ratings) / len(ratings)) \
                 if ratings else 0

    versions = ",".join(
        [beatmap.version for beatmap in set.beatmaps]
    )

    return "|".join([
        str(set.id), # .osz filename
        set.artist,
        set.title,
        set.creator,
        {
            -2: "3",
            -1: "3",
            0: "3",
            1: "1",
            2: "2",
            3: "1",
            4: "2"
        }[set.status],
        avg_rating,
        str(set.last_update),
        str(set.id),
        str(int(False)), # TODO: hasVideo
        str(int(False)), # TODO: hasStoryboard,
        str(0), # TODO: Filesize
        versions,
        str(set.id), # TODO: postId
    ])
