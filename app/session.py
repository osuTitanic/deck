
from .common.database import Postgres
from .common.storage import Storage
from .common.users import UserCache

from requests import Session

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

storage = Storage()

cache = UserCache()
