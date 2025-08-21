from __future__ import annotations

import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..utils.auth import get_current_admin
from ..utils.backup import (
    create_backup,
    save_backup_to_disk,
    prune_old_backups,
)

router = APIRouter(prefix="/backup", tags=["Backup"])


@router.get("/", response_class=StreamingResponse, dependencies=[Depends(get_current_admin)])
async def backup_database():
    """
    One-off backup download (unchanged).
    Streams a temporary pg_dump file back to the client.
    """
    return create_backup()


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default


@router.post("/save", dependencies=[Depends(get_current_admin)])
async def backup_save_to_disk():
    """
    Admin-only endpoint intended for periodic schedulers (e.g. cron/healthcheck).
    Behavior:
      - If AUTOBACKUPS=no (default in .env), returns a no-op response.
      - If enabled, writes BACKUP_DIR/gamecubby_DDMMYY.dump (overwrites per day),
        then prunes backups older than BACKUP_RETENTION_DAYS.

    Returns JSON with:
      {
        "ok": true|false,
        "message": "...",
        "saved_path": "/abs/path/to/file" | null,
        "saved_bytes": 12345 | 0,
        "deleted": [".../old1.dump", ".../old2.dump"],
        "retention_days": 14,
        "autobackups": true|false
      }
    """
    autobackups = _env_bool("AUTOBACKUPS", False)
    retention_days = _env_int("BACKUP_RETENTION_DAYS", 14)

    if not autobackups:
        return {
            "ok": False,
            "message": "AUTOBACKUPS is disabled; no action taken.",
            "saved_path": None,
            "saved_bytes": 0,
            "deleted": [],
            "retention_days": retention_days,
            "autobackups": False,
        }

    saved: Path = save_backup_to_disk()
    size = saved.stat().st_size if saved.exists() else 0

    deleted_paths: List[Path] = prune_old_backups(retention_days)
    deleted = [str(p) for p in deleted_paths]

    return {
        "ok": True,
        "message": "Backup saved and retention pruning completed.",
        "saved_path": str(saved),
        "saved_bytes": size,
        "deleted": deleted,
        "retention_days": retention_days,
        "autobackups": True,
    }
