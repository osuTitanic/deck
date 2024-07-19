
from . import highlights
from . import session
from . import routes

from .common.logging import Console, File

from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError

from fastapi import (
    HTTPException,
    Response,
    Request,
    FastAPI
)

import logging
import uvicorn
import config
import utils

utils.setup()

logging.basicConfig(
    format='[%(asctime)s] - <%(name)s> %(levelname)s: %(message)s',
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    handlers=[Console, File]
)

if logging.getLogger('uvicorn.access').handlers:
    # Redirect uvicorn logs to file
    logging.getLogger('uvicorn.access').addHandler(File)
    logging.getLogger('uvicorn.error').addHandler(File)

# Disable multipart warnings (https://github.com/osuAkatsuki/bancho.py/pull/674)
logging.getLogger('multipart.multipart').setLevel(logging.ERROR)

api = FastAPI(
    title='Deck',
    description='API for osu! clients',
    version=config.VERSION,
    redoc_url=None if not config.DEBUG else '/redoc',
    docs_url=None if not config.DEBUG else '/docs',
    debug=True if config.DEBUG else False
)

@api.exception_handler(HTTPException)
def exception_handler(request: Request, exc: HTTPException):
    headers = exc.headers if exc.headers else {}
    headers.update({'detail': exc.detail})

    return Response(
        status_code=exc.status_code,
        headers=headers
    )

@api.exception_handler(StarletteHTTPException)
def exception_handler(request: Request, exc: StarletteHTTPException):
    return Response(
        status_code=exc.status_code,
        headers={'detail': exc.detail}
    )

@api.exception_handler(RequestValidationError)
def validation_error(request: Request, exc: RequestValidationError):
    session.logger.error(f"Validation error: {exc.errors()}")
    return Response(
        status_code=400,
        content='no'
    )

api.include_router(routes.router)

def run():
    uvicorn.run(
        api,
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        log_config=None
    )
