import logging

logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from typing import AsyncIterator
from fastapi import FastAPI

from .db import get_db
from .utils.auth import ensure_default_admin
from .utils.playerperspective import sync_player_perspectives
from .utils.mode import sync_modes_from_igdb
from .utils.genre import sync_genres
from .utils.storage import ensure_game_folders
from .utils.location import create_location, list_all_locations

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
from .routers.company import router as company_router
from .routers.search import router as search_router
from .routers.auth import router as auth_router

import os

# print("[DEBUG] SECRET_KEY =", os.getenv("SECRET_KEY"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_game_folders(autocreate_all=True)

    db = next(get_db())
    try:
        ensure_default_admin(db)

        # Ensure there's at least one location (create default root if missing)
        if not list_all_locations(db):
            print("[Startup] No locations found. Creating 'Default Storage' root.")
            create_location(db, name="Default Storage", parent_id=None, type="root")

        await sync_player_perspectives(db)
        await sync_modes_from_igdb(db)
        await sync_genres(db)

    except Exception as e:
        print(f"[Startup Sync Warning] Failed: {e}")

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
app.include_router(company_router)
app.include_router(search_router)
app.include_router(auth_router)


@app.get("/")
def read_root():
    return {
        "app_name": "GameCubby API",
        "version": "0.1",
        "build_name": "Three-headed monkey",
        "build_time": 1752871163
    }
