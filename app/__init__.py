
from . import performance
from . import logging
from . import session
from . import routes

from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError

from fastapi import (
    HTTPException,
    Response,
    Request,
    FastAPI
)

import uvicorn
import config

api = FastAPI(
    title='Deck',
    description='API for osu! clients',
    version=config.VERSION,
    redoc_url=None,
    docs_url=None
)

@api.exception_handler(HTTPException)
async def exception_handler(request: Request, exc: HTTPException):
    headers = exc.headers if exc.headers else {}
    headers.update({'detail': exc.detail})

    return Response(
        status_code=exc.status_code,
        headers=headers
    )

@api.exception_handler(StarletteHTTPException)
async def exception_handler(request: Request, exc: HTTPException):
    headers = exc.headers if exc.headers else {}
    headers.update({'detail': exc.detail})

    return Response(
        status_code=exc.status_code,
        headers=headers
    )

@api.exception_handler(RequestValidationError)
def validation_error(request: Request, exc: RequestValidationError):
    return Response(
        status_code=400,
        content='no'
    )

api.include_router(routes.router)

def run():
    uvicorn.run(api, host=config.WEB_HOST, port=config.WEB_PORT, log_config=None)
