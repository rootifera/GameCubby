import json
import logging
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path

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

from .utils.backup import save_backup_to_disk, prune_old_backups

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


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Startup tasks, but skip DB work entirely if maintenance mode is enabled.
    Also optionally runs a daily auto-backup loop if AUTOBACKUPS=yes.
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

    stop_event = asyncio.Event()

    async def backup_loop() -> None:
        if not _env_bool("AUTOBACKUPS", False):
            return
        bt = (os.getenv("BACKUP_TIME", "03:00") or "03:00").strip()
        try:
            hh_str, mm_str = bt.split(":", 1)
            hh, mm = int(hh_str), int(mm_str)
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError
        except Exception:
            print(f"[autobackup] Invalid BACKUP_TIME='{bt}', defaulting to 03:00")
            hh, mm = 3, 0

        try:
            retention_days = int(os.getenv("BACKUP_RETENTION_DAYS", "14") or "14")
        except Exception:
            retention_days = 14

        print(f"[autobackup] enabled: time={hh:02d}:{mm:02d} retention={retention_days}d")

        while not stop_event.is_set():
            now = datetime.now()
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            sleep_s = max(0.0, (target - now).total_seconds())

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=sleep_s)
                break
            except asyncio.TimeoutError:
                pass

            try:
                fpath = save_backup_to_disk()
                prune_old_backups(retention_days)
                print(f"[autobackup] backup saved: {fpath}")
            except Exception as e:
                print(f"[autobackup] backup failed: {e}")

    backup_task = asyncio.create_task(backup_loop())

    yield

    stop_event.set()
    try:
        await backup_task
    except Exception:
        pass


app = FastAPI(lifespan=lifespan)


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


_version_path = Path(__file__).with_name("version.json")
try:
    with open(_version_path, "r", encoding="utf-8") as f:
        _version_info = json.load(f)
except Exception:
    _version_info = {
        "app_name": "GameCubby API",
        "version": "unknown",
        "build_name": "unknown",
        "build_time": 0,
    }


@app.get("/")
def read_root():
    return _version_info
