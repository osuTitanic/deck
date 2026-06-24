
from .common.helpers.performance import ppv2, ppv2_rosu
from .common.helpers.beatmaps import BeatmapResources
from .common.cache.events import EventQueue
from .common.database import Postgres
from .common.storage import Storage
from .common.config import Config

from concurrent.futures import ThreadPoolExecutor
from requests import Session
from redis import Redis

import logging

logger = logging.getLogger('deck')
config = Config()

requests = Session()
requests.headers = {
    'User-Agent': f'osuTitanic/deck {config.DOMAIN_NAME}'
}

redis = Redis(
    config.REDIS_HOST,
    config.REDIS_PORT
)

events = EventQueue(
    name='bancho:events',
    connection=redis
)

database = Postgres(config)
storage = Storage(config)
beatmaps = BeatmapResources(storage, redis)

# Used for achievements checks
achievement_executor = ThreadPoolExecutor(max_workers=5)

# Used for uploading replays, and checking hightlights
score_executor = ThreadPoolExecutor(max_workers=5)

# Initialize ppv2 calculator
instance = ppv2_rosu.RosuPerformanceCalculator(beatmaps)
ppv2.initialize_calculator(instance)
