import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from dotenv import load_dotenv
from .utils.storage import ensure_game_folders
from .routers import igdb
from .routers.tags import router as tags_router
from .routers.locations import router as locations_router
from .routers.platforms import router as platforms_router
from .routers.games import router as games_router
from .routers.collections import router as collections_router
from .routers.storage import router as storage_router
from .routers.storage import system_files_router as sync_storage_router
from .routers.storage import downloads_router as downloads_router
from .routers.modes import router as modes_router
from .routers.genres import router as genres_router

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_game_folders(autocreate_all=True)
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(igdb.router, prefix="/igdb")
app.include_router(tags_router)
app.include_router(locations_router)
app.include_router(platforms_router)
app.include_router(games_router)
app.include_router(collections_router)
app.include_router(storage_router)
app.include_router(sync_storage_router)

app.include_router(downloads_router)

app.include_router(modes_router)
app.include_router(genres_router)


@app.get("/")
def read_root():
    return {
        "app_name": "GameCubby API",
        "version": "0.1",
        "build_name": "Three-headed monkey",
        "build_time": 1752871163
    }
