
from .common.database import Postgres

from requests import Session
from redis import Redis

import logging
import config

logger = logging.getLogger('deck')

requests = Session()
requests.headers = {
    'User-Agent': f'deck-{config.VERSION}'
}

database = Postgres(
    config.POSTGRES_USER,
    config.POSTGRES_PASSWORD,
    config.POSTGRES_HOST,
    config.POSTGRES_PORT
)

redis = Redis(
    config.REDIS_HOST,
    config.REDIS_PORT
)
