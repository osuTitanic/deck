
from .common.cache.events import EventQueue
from .common.database import Postgres
from .common.storage import Storage

from concurrent.futures import ThreadPoolExecutor
from requests import Session
from redis import Redis

import logging
import config

logger = logging.getLogger('deck')

requests = Session()
requests.headers = {
    'User-Agent': f'deck-{config.VERSION}'
}

redis = Redis(
    config.REDIS_HOST,
    config.REDIS_PORT
)

events = EventQueue(
    name='bancho:events',
    connection=redis
)

database = Postgres(
    config.POSTGRES_USER,
    config.POSTGRES_PASSWORD,
    config.POSTGRES_HOST,
    config.POSTGRES_PORT
)

# Used for achievements checks
achievement_executor = ThreadPoolExecutor(max_workers=15)

# Used for uploading replays, and checking hightlights
executor = ThreadPoolExecutor(max_workers=10)

storage = Storage()
