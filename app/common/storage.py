
from boto3_type_annotations.s3 import Client
from botocore.exceptions import ClientError

from datetime import timedelta
from typing import Optional
from redis import Redis

import logging
import config
import boto3
import io

class Storage:
    """This class aims to provide a higher level api for using/managing storage."""

    def __init__(self) -> None:
        self.logger = logging.getLogger('storage')

        self.cache = Redis(
            config.REDIS_HOST,
            config.REDIS_PORT
        )

        self.s3: Client = boto3.client(
            's3',
            endpoint_url=config.S3_BASEURL,
            aws_access_key_id=config.S3_ACCESS_KEY,
            aws_secret_access_key=config.S3_SECRET_KEY
        )

    # TODO: Replays, Screenshots, etc...

    def get_avatar(self, id: str) -> Optional[bytes]:
        if (image := self.get_from_cache(f'avatar:{id}')):
            return image

        if config.S3_ENABLED:
            if not (image := self.get_from_s3(str(id), 'avatars')):
                return

        else:
            if not (image := self.get_file_content(f'/avatars/{id}')):
                return

        self.save_to_cache(
            name=f'avatar:{id}',
            content=image,
            expiry=timedelta(days=1)
        )

        return image

    def save_to_cache(self, name: str, content: bytes, expiry=timedelta(weeks=1), override=True) -> bool:
        return self.cache.set(name, content, expiry, nx=(not override))

    def save_to_file(self, filepath: str, content: bytes) -> bool:
        try:
            with open(f'{config.DATA_PATH}/{filepath}', 'wb') as f:
                f.write(content)
        except Exception as e:
            self.logger.error(f'Failed to save file "{filepath}": {e}')
            return False

        return True

    def save_to_s3(self, content: bytes, key: str, bucket: str) -> bool:
        try:
            self.s3.upload_fileobj(
                io.BytesIO(content),
                bucket,
                key
            )
        except Exception as e:
            self.logger.error(f'Failed to upload "{key}" to s3: "{e}"')
            return False

        return True

    def get_from_cache(self, name: str) -> Optional[bytes]:
        return self.cache.get(name)

    def get_file_content(self, filepath: str) -> Optional[bytes]:
        try:
            with open(f'{config.DATA_PATH}/{filepath}', 'wb') as f:
                return f.read()
        except Exception as e:
            self.logger.error(f'Failed to read file "{filepath}": {e}')

    def get_from_s3(self, key: str, bucket: str) -> Optional[bytes]:
        buffer = io.BytesIO()

        try:
            self.s3.download_fileobj(
                bucket,
                key,
                buffer
            )
        except ClientError:
            # Most likely not found
            return
        except Exception as e:
            self.logger.error(f'Failed to download "{key}" from s3: "{e}"')
            return

        return buffer.getvalue()
