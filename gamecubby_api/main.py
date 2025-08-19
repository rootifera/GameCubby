import logging

from .utils.app_config import get_app_config_value

logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)

from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager
from typing import AsyncIterator
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .utils.playerperspective import sync_player_perspectives
from .utils.mode import sync_modes
from .utils.genre import sync_genres
from .utils.storage import ensure_game_folders
from .utils.location import create_location, list_all_locations

from .utils.maintenance import (
    is_maintenance_enabled,
    allowed_in_maintenance,
)

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
from .routers.app_config import router as appconfig_router
from .routers.setup import router as setup_router
from .routers.export import router as export_router
from .routers.backups import router as backups_router
from .routers.stats import router as stats_router
from .routers.maintenance import router as maintenance_router

from .utils.db_tools import with_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Startup tasks, but skip DB work entirely if maintenance mode is enabled.
    """
    ensure_game_folders(autocreate_all=True)

    if not is_maintenance_enabled():
        with with_db() as db:
            try:
                if not list_all_locations(db):
                    print("[Startup] No locations found. Creating 'Default Storage' root.")
                    create_location(db, name="Default Storage", parent_id=None, type="root")

                if get_app_config_value(db, "is_firstrun_done") == "true":
                    await sync_player_perspectives(db)
                    await sync_modes(db)
                    await sync_genres(db)

            except Exception as e:
                print(f"[Startup Sync Warning] Failed: {e}")
    else:
        print("[Startup] Maintenance enabled — skipping DB initialization.")

    yield


app = FastAPI(lifespan=lifespan)

# ----------------------------
# Maintenance middleware gate
# ----------------------------
# Blocks everything while maintenance is ON, except an allow-list.
# The default allow-list in utils.maintenance includes:
#   - /admin/maintenance/...
#   - /health

@app.middleware("http")
async def maintenance_gate(request: Request, call_next):
    path = request.url.path

    if allowed_in_maintenance(path):
        return await call_next(request)

    if is_maintenance_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Maintenance in progress",
                "path": path,
                "hint": "Only /admin/maintenance/* and /health are available during maintenance.",
            },
            headers={"Retry-After": "60"},
        )

    return await call_next(request)


app.include_router(auth_router)
app.include_router(appconfig_router)
app.include_router(setup_router)
app.include_router(igdb.router, prefix="/igdb")
app.include_router(games_router)
app.include_router(collections_router)
app.include_router(tags_router)
app.include_router(genres_router)
app.include_router(modes_router)
app.include_router(platforms_router)
app.include_router(perspectives_router)
app.include_router(locations_router)
app.include_router(company_router)
app.include_router(search_router)
app.include_router(storage_router)
app.include_router(sync_storage_router)
app.include_router(downloads_router)
app.include_router(export_router)
app.include_router(backups_router)
app.include_router(stats_router)
app.include_router(maintenance_router)

@app.get("/health")
def health():
    return {"ok": True, "service": "GameCubby API", "maintenance": is_maintenance_enabled()}


@app.get("/")
def read_root():
    return {
        "app_name": "GameCubby API",
        "version": "1.1",
        "build_name": "Guybrush Threepwood",
        "build_time": 1755523354
    }
