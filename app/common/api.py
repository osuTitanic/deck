
from requests import Session
from typing import Optional

import logging
import config

class Beatmaps:
    """Wrapper for different beatmap resources, using different API's"""

    def __init__(self) -> None:
        self.logger = logging.getLogger('beatmap-api')

        self.session = Session()
        self.session.headers = {
            'User-Agent': f'deck-{config.VERSION}'
        }

    def log_error(self, url: str, status_code: int) -> None:
        self.logger.error(f'Error while sending request to "{url}" ({status_code})')

    def osz(self, set_id: int) -> Optional[bytes]:
        self.logger.debug(f'Downloading osz... ({set_id})')

        response = self.session.get(f'https://osu.direct/api/d/{set_id}')

        if not response.ok:
            self.log_error(response.url, response.status_code)
            return

        # NOTE: osu.direct always responds with status code 200, even on errors
        # So here is a little workaround for that

        if 'application/json' in response.headers['Content-Type']:
            self.log_error(response.url, response.json()['code'])
            return

        return response.content
    
    def osu(self, beatmap_id: int) -> Optional[bytes]:
        self.logger.debug(f'Downloading beatmap... ({beatmap_id})')

        response = self.session.get(f'https://osu.direct/api/osu/{beatmap_id}')

        if not response.ok:
            self.log_error(response.url, response.status_code)
            return

        if 'application/json' in response.headers['Content-Type']:
            self.log_error(response.url, response.json()['code'])
            return

        return response.content

    def preview(self, set_id: int) -> Optional[bytes]:
        self.logger.debug(f'Downloading preview... ({set_id})')

        response = self.session.get(f'https://b.ppy.sh/preview/{set_id}.mp3')

        if not response.ok:
            self.log_error(response.url, response.status_code)
            return

        return response.content

    def background(self, set_id: int, large=False) -> Optional[bytes]:
        self.logger.debug(f'Downloading background... ({set_id})')

        response = self.session.get(f'https://b.ppy.sh/thumb/{set_id}{"l" if large else ""}.jpg')

        if not response.ok:
            self.log_error(response.url, response.status_code)
            return

        return response.content
