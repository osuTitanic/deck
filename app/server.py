
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from app import session
from . import routes

import config
import utils

@asynccontextmanager
async def lifespan(app: FastAPI):
    utils.setup()
    session.database.wait_for_connection()
    session.redis.ping()
    yield
    session.achievement_executor.shutdown(wait=True)
    session.executor.shutdown(wait=True)
    session.database.engine.dispose()
    session.redis.close()

api = FastAPI(
    title='Deck',
    description='API for osu! clients',
    version=config.VERSION,
    redoc_url=None if not config.DEBUG else '/redoc',
    docs_url=None if not config.DEBUG else '/docs',
    debug=True if config.DEBUG else False,
    lifespan=lifespan
)
api.include_router(routes.router)
