
from app.common.config import config_instance as config
from pydub import AudioSegment
from functools import cache
from typing import Callable
from functools import wraps
from PIL import Image

import bcrypt
import lzma
import time
import app
import io
import re
import os

REQUIRED_STORAGE_KEYS = (
    'screenshots',
    'thumbnails',
    'beatmaps',
    'avatars',
    'replays',
    'release',
    'audio',
    'osz2',
    'osz'
)

def setup() -> None:
    os.makedirs(
        f'{config.DATA_PATH}/logs',
        exist_ok=True
    )

    if not config.S3_ENABLED:
        setup_data_folder()
        return

    return setup_s3_buckets()

def setup_data_folder() -> None:
    # Create required folders if not they not already exist
    for bucket in REQUIRED_STORAGE_KEYS:
        os.makedirs(
            f'{config.DATA_PATH}/{bucket}',
            exist_ok=True
        )

    if any(os.scandir(f'{config.DATA_PATH}/avatars')):
        return

    app.session.logger.info('Downloading default avatars...')
    download_to_file(f'{config.DATA_PATH}/avatars/unknown', 'https://github.com/osuTitanic/titanic/blob/main/.github/images/avatars/unknown.jpg?raw=true')
    download_to_file(f'{config.DATA_PATH}/avatars/1', 'https://github.com/osuTitanic/titanic/blob/main/.github/images/avatars/banchobot.jpg?raw=true')

def setup_s3_buckets() -> None:
    bucket_list = app.session.storage.s3.list_buckets()

    # Create required buckets if needed
    buckets = [
        bucket['Name']
        for bucket in bucket_list['Buckets']
    ]

    for bucket in REQUIRED_STORAGE_KEYS:
        if bucket in buckets:
            continue

        app.session.logger.info(f'Creating bucket: "{bucket}"')
        app.session.storage.s3.create_bucket(Bucket=bucket)

        if bucket != 'avatars':
            continue

        app.session.logger.info('Downloading default avatars...')
        download_to_s3('avatars', 'unknown', 'https://github.com/osuTitanic/titanic/blob/main/.github/images/avatars/unknown.jpg?raw=true')
        download_to_s3('avatars', '1', 'https://github.com/osuTitanic/titanic/blob/main/.github/images/avatars/banchobot.jpg?raw=true')

def download_to_file(path: str, url: str) -> None:
    if os.path.isfile(path):
        return

    response = app.session.requests.get(url, allow_redirects=True)

    if not response.ok:
        app.session.logger.error(f'Failed to download file: {url}')
        return

    with open(path, 'wb') as f:
        f.write(response.content)

def download_to_s3(bucket: str, key: str, url: str) -> None:
    response = app.session.requests.get(url)

    if not response.ok:
        app.session.logger.error(f'Failed to download file to s3: {url}')
        return

    return app.session.storage.save_to_s3(
        response.content,
        key,
        bucket
    )

unsafe_characters_pattern = re.compile(r'[<>:"/\\|?*\x00-\x1F]')

def sanitize_filename(filename: str) -> str:
    return re.sub(unsafe_characters_pattern, "", filename)

def empty_zip_file() -> bytes:
    return b'PK\x05\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'

@cache
def check_password(password: str, bcrypt_hash: str) -> bool:
    if len(password) != 32:
        # We expect an md5 hash to be passed as password
        return False

    return bcrypt.checkpw(
        password.encode(),
        bcrypt_hash.encode()
    )

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

def resize_image(
    image: bytes,
    target_size: int | None = None,
) -> bytes:
    img = Image.open(io.BytesIO(image))
    img = img.resize((target_size, target_size))
    image_buffer = io.BytesIO()
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

def measure_time(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        elapsed_time = end_time - start_time
        app.session.logger.info(f'"{func.__name__}" took {elapsed_time:.4f} seconds')
        return result
    return wrapper

def lzma_decompress(data, format=lzma.FORMAT_AUTO, memlimit=None, filters=None, max_length: int = -1):
    """Modified 'lzma.decompress' function, that allows to set a max_length"""
    chunks = []

    while True:
        try:
            decomp = lzma.LZMADecompressor(format, memlimit, filters)
            res = decomp.decompress(data, max_length)
        except lzma.LZMAError:
            if chunks:
                # Leftover data is not a valid LZMA/XZ stream; ignore it.
                break
            else:
                # Error on the first iteration; bail out.
                raise

        if not decomp.eof:
            raise lzma.LZMAError("Compressed data ended before the end-of-stream marker was reached")

        chunks.append(res)
        data = decomp.unused_data

        if not data:
            break

    return b"".join(chunks)
