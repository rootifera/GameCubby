from __future__ import annotations

import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..utils.auth import get_current_admin
from ..utils.backup import (
    create_backup,
    save_backup_to_disk,
    prune_old_backups,
    list_backups,
    sync_backup_storage,
)
from pydantic import BaseModel

router = APIRouter(prefix="/backup", tags=["Backup"])


@router.get("/", response_class=StreamingResponse, dependencies=[Depends(get_current_admin)])
async def backup_database():
    """
    One-off backup download (unchanged).
    Streams a temporary pg_dump file back to the client.
    """
    return create_backup()


@router.get("/list", dependencies=[Depends(get_current_admin)])
async def backup_list(db: Session = Depends(get_db)):
    return {"ok": True, "files": list_backups(db)}


class BackupStorageSyncRequest(BaseModel):
    source: str
    target: str


@router.post("/sync-storage", dependencies=[Depends(get_current_admin)])
async def backup_sync_storage(payload: BackupStorageSyncRequest, db: Session = Depends(get_db)):
    try:
        return {"ok": True, **sync_backup_storage(db, payload.source, payload.target)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
async def backup_save_to_disk(db: Session = Depends(get_db)):
    """
    Admin-only endpoint intended for periodic schedulers (e.g. cron/healthcheck).
    Behavior:
      - Writes a backup to the configured backup storage backend.
      - Prunes old auto backups based on BACKUP_RETENTION_DAYS.

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
    retention_days = _env_int("BACKUP_RETENTION_DAYS", 14)

    saved = save_backup_to_disk(db)

    deleted: List[str] = prune_old_backups(db, retention_days)

    return {
        "ok": True,
        "message": "Backup saved and retention pruning completed.",
        "saved_path": saved.uri,
        "saved_bytes": saved.size,
        "deleted": deleted,
        "retention_days": retention_days,
        "autobackups": _env_bool("AUTOBACKUPS", False),
    }
