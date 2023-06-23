
from requests import Session

import logging
import config

logger = logging.getLogger('deck')

requests = Session()
requests.headers = {
    'User-Agent': f'deck-{config.VERSION}'
}
