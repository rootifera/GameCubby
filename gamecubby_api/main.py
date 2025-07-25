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
from .routers.playerperspectives import router as perspectives_router

from .utils.playerperspective import sync_player_perspectives
from .utils.mode import sync_modes_from_igdb
from .utils.genre import sync_genres
from .db import get_db

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_game_folders(autocreate_all=True)

    db = next(get_db())
    try:
        await sync_player_perspectives(db)
        await sync_modes_from_igdb(db)
        await sync_genres(db)
    except Exception as e:
        print(f"[Startup Sync Warning] Failed to sync some IGDB data: {e}")

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
app.include_router(perspectives_router)


@app.get("/")
def read_root():
    return {
        "app_name": "GameCubby API",
        "version": "0.1",
        "build_name": "Three-headed monkey",
        "build_time": 1752871163
    }
