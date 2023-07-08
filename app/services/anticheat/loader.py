
from circleguard.loader import Loader as CircleguardLoader

import logging
import app

class Loader(CircleguardLoader):
    def __init__(self, key, cache_path=None, write_to_cache=True):
        self.log = logging.getLogger('anticheat-loader')
        self.api = None

        self._conn = None
        self._cursor = None
        self.write_to_cache = write_to_cache and bool(cache_path)
        self.read_from_cache = bool(cache_path)

    def beatmap_id(self, beatmap_hash: str):
        if not (beatmap := app.session.database.beatmap_by_checksum(beatmap_hash)):
            return 0

        return beatmap.id

    def user_id(self, username):
        if not (user := app.session.database.user_by_name(username)):
            return 0

        return user.id

    def username(self, user_id):
        if not (user := app.session.database.user_by_id(user_id)):
            return ''

        return user.name
