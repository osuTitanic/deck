
from . import logging
from . import session
from . import routes

from fastapi import FastAPI

import uvicorn
import config

api = FastAPI(
    title='Deck',
    description='API for osu! clients',
    docs_url=None
)

api.include_router(routes.router)

def run():
    uvicorn.run(api, host=config.WEB_HOST, port=config.WEB_PORT, log_config=None)
