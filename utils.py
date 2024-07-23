
from __future__ import annotations

from app.common.database.repositories import beatmapsets
from app.common.helpers import analytics, ip
from app.common.database import DBUser
from app.common.cache import status

from concurrent.futures import Future
from pydub import AudioSegment
from functools import cache
from fastapi import Request
from PIL import Image

import config
import bcrypt
import app
import io
import os

REQUIRED_BUCKETS = [
    'screenshots',
    'beatmaps',
    'avatars',
    'replays',
    'release',
    'audio',
    'thumbnails',
    'osz',
    'osz2'
]

def download_to_file(path: str, url: str):
    if os.path.isfile(path):
        return

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

    return app.session.storage.save_to_s3(
        response.content,
        key,
        bucket
    )

def setup():
    os.makedirs(f'{config.DATA_PATH}/logs', exist_ok=True)

    if not config.S3_ENABLED:
        # Create required folders if not they not already exist
        for bucket in REQUIRED_BUCKETS:
            os.makedirs(
                f'{config.DATA_PATH}/{bucket}',
                exist_ok=True
            )

        if os.listdir(f'{config.DATA_PATH}/avatars'):
            return

        app.session.logger.info('Downloading default avatars...')

        download_to_file(f'{config.DATA_PATH}/avatars/unknown', 'https://github.com/lekuru-static/download/blob/main/unknown?raw=true')
        download_to_file(f'{config.DATA_PATH}/avatars/1', 'https://github.com/lekuru-static/download/blob/main/1?raw=true')
        return

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

        if bucket != 'avatars':
            continue

        app.session.logger.info('Downloading default avatars...')

        download_to_s3('avatars', 'unknown', 'https://github.com/lekuru-static/download/blob/main/unknown?raw=true')
        download_to_s3('avatars', '1', 'https://github.com/lekuru-static/download/blob/main/1?raw=true')

def has_jpeg_headers(data_view: memoryview) -> bool:
    return (
        data_view[:4] == b"\xff\xd8\xff\xe0"
        and data_view[6:11] == b"JFIF\x00"
    )

def has_png_headers(data_view: memoryview) -> bool:
    return (
        data_view[:8] == b"\x89PNG\r\n\x1a\n"
        and data_view[-8] == b"\x49END\xae\x42\x60\x82"
    )

def get_osz_size(set_id: int, no_video: bool = False) -> int:
    r = app.session.requests.head(f'https://api.osu.direct/d/{set_id}{"noVideo=" if no_video else ""}')

    if not r.ok:
        app.session.logger.error(
            f"Failed to get osz size: {r.status_code}"
        )
        return 0

    if not (filesize := r.headers.get('content-length')):
        app.session.logger.error(
            "Failed to get osz size: content-length header missing"
        )
        return 0

    return int(filesize)

def update_osz_filesize(set_id: int, has_video: bool = False):
    updates = {}

    if has_video:
        updates['osz_filesize_novideo'] = get_osz_size(
            set_id,
            no_video=True
        )

    updates['osz_filesize'] = get_osz_size(
        set_id,
        no_video=False
    )

    beatmapsets.update(set_id, updates)

def resize_image(
    image: bytes,
    target_width: int | None = None,
    target_height: int | None = None,
    max_width: int | None = None,
    max_height: int | None = None
) -> bytes:
    img = Image.open(io.BytesIO(image))
    image_width, image_height = img.size

    if (target_width is None) or (target_height is None):
        if target_height:
            target_width = round((image_width / image_height) * min(target_height, 2000))

        if target_width:
            target_height = round((image_height / image_width) * min(target_width, 2000))

        else:
            raise ValueError('At least one value must be given.')

    image_buffer = io.BytesIO()

    target_width = min(max_height, target_height) if max_height else target_height
    target_width = min(max_width, target_width) if max_width else target_width

    img = img.resize((target_width, target_height))
    img.save(image_buffer, format='PNG')

    return image_buffer.getvalue()

def resize_and_crop_image(
    image: bytes,
    target_width: int,
    target_height: int
) -> bytes:
    img = Image.open(io.BytesIO(image))
    image_width, image_height = img.size

    aspect = image_width / float(image_height)
    target_aspect = target_width / float(target_height)

    if aspect > target_aspect:
        # Crop off left and right
        new_width = int(image_height * target_aspect)
        offset = (image_width - new_width) / 2
        box = (offset, 0, image_width - offset, image_height)

    else:
        # Crop off top and bottom
        new_height = int(image_width / target_aspect)
        offset = (image_height - new_height) / 2
        box = (0, offset, image_width, image_height - offset)

    image_buffer = io.BytesIO()
    img = img.crop(box)
    img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    img.convert('RGB').save(image_buffer, format='JPEG')
    return image_buffer.getvalue()

def extract_audio_snippet(
    audio: bytes,
    offset_ms: int,
    duration_ms: int = 10000,
    bitrate: int = '64k'
) -> bytes:
    # Load audio and extract snippet
    audio = AudioSegment.from_file(io.BytesIO(audio))

    if offset_ms < 0:
        # Set default offset
        audio_length = audio.duration_seconds * 1000
        offset_ms = audio_length / 2.5

    snippet = audio[offset_ms:offset_ms + duration_ms]

    # Export snippet as mp3
    snippet_buffer = io.BytesIO()
    snippet.export(snippet_buffer, format='mp3', bitrate=bitrate)
    return snippet_buffer.getvalue()

def thread_callback(future: Future):
    if e := future.exception():
        app.session.database.logger.error(
            f'Failed to execute thread: {e}',
            exc_info=e
        )
        return

    app.session.database.logger.debug(
        f'Thread completed: {e}',
        exc_info=e
    )

def track(
    event: str,
    properties: dict,
    user: DBUser | None,
    request: Request
) -> None:
    if not user:
        return

    if not status.exists(user.id):
        return

    ip_address = ip.resolve_ip_address_fastapi(request)
    device_id = status.device_id(user.id)
    version = status.version(user.id)

    analytics.track(
        event,
        user_id=user.id,
        device_id=device_id,
        app_version=version,
        ip=ip_address,
        event_properties=properties,
        user_properties={
            'user_id': user.id,
            'name': user.name,
            'country': user.country
        }
    )

@cache
def check_password(password: str, bcrypt_hash: str) -> bool:
    return bcrypt.checkpw(
        password.encode(),
        bcrypt_hash.encode()
    )
