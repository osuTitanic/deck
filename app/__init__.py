
from .common.logging import Console, File
from .server import api

from . import exceptions
from . import session
from . import routes
from . import server
from . import utils

import logging
import uvicorn

logging.basicConfig(
    format='[%(asctime)s] - <%(name)s> %(levelname)s: %(message)s',
    level=logging.DEBUG if session.config.DEBUG else logging.INFO,
    handlers=[Console, File]
)

# Disable multipart warnings (https://github.com/osuAkatsuki/bancho.py/pull/674)
logging.getLogger('multipart.multipart').setLevel(logging.ERROR)

# Redirect uvicorn logs to file, if they exist
if logging.getLogger('uvicorn.access').handlers:
    logging.getLogger('uvicorn.access').addHandler(File)
    logging.getLogger('uvicorn.error').addHandler(File)

def run():
    uvicorn.run(
        server.api,
        host=session.config.WEB_HOST,
        port=session.config.WEB_PORT,
        log_config=None
    )
