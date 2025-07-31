
from app import session, utils, routes, profiling
from contextlib import asynccontextmanager
from fastapi import FastAPI

import config

@asynccontextmanager
async def lifespan(app: FastAPI):
    session.database.engine.dispose()
    session.database.wait_for_connection()
    session.redis.ping()
    profiling.setup()
    utils.setup()
    yield
    session.achievement_executor.shutdown(wait=True)
    session.score_executor.shutdown(wait=True)
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
