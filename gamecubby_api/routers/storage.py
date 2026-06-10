from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, Form, File, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, constr
from datetime import datetime, timezone
from pathlib import Path
import json
import os

from ..db import get_db
from ..models.game import Game
from ..models.storage import GameFile
from ..schemas.storage import FileResponse, FileCategory
from ..utils.storage import (
    upload_and_register_file, sanitize_filename, delete_game_file,
    sync_game_files, sync_all_files, get_downloadable_file, update_file_label
)
from ..utils.storage import configured_storage_backend, sync_storage_backends
from ..utils.auth import get_current_admin, get_current_admin_optional
from ..utils.app_config import get_app_config_value
from ..utils.db_tools import with_db

import logging

logger = logging.getLogger(__name__)

SYNC_STATUS_FILE = Path(os.getenv("FILE_SYNC_STATUS_FILE", "storage/file_sync_status.json"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_sync_status() -> dict:
    try:
        if SYNC_STATUS_FILE.is_file():
            return json.loads(SYNC_STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to read file sync status from %s", SYNC_STATUS_FILE)
    return {
        "status": "idle",
        "detail": "No sync has run yet.",
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }


def _write_sync_status(payload: dict) -> None:
    SYNC_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = SYNC_STATUS_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(SYNC_STATUS_FILE)

router = APIRouter(prefix='/games/{game_id}/files', tags=['Files'])
system_files_router = APIRouter(prefix='/files', tags=['Scan All Files'])
downloads_router = APIRouter(prefix='/downloads', tags=['Downloads'])


@router.get('/', response_model=List[FileResponse])
def list_files(
    game_id: int,
    category: Optional[FileCategory] = Query(None, description="Filter by content category"),
    db: Session = Depends(get_db),
) -> List[FileResponse]:
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    game_ref = str(game.igdb_id) if game.igdb_id else "".join(c for c in game.name.lower() if c.isalnum())

    q = db.query(GameFile).filter(GameFile.game == game_ref)
    q = q.filter(GameFile.storage_backend == configured_storage_backend(db))
    if category is not None:
        q = q.filter(GameFile.category == category)

    files = q.all()
    return files


@router.post('/upload', response_model=dict)
async def upload_file(
        game_id: int,
        label: str = Form(...),
        category: FileCategory = Form(...),  # required content category
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        admin=Depends(get_current_admin)
) -> dict:
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    safe_name = sanitize_filename(file.filename)

    try:
        file_record = await upload_and_register_file(
            db=db,
            game=game,
            upload_file=file,
            label=label,
            safe_filename=safe_name,
            category=category,
        )
        return {
            "file_id": file_record.id,
            "path": file_record.path,
            "game_ref": file_record.game,
            "category": file_record.category.value if hasattr(file_record.category, "value") else file_record.category,
        }
    except ValueError as e:
        if "already exists" in str(e) or "already registered" in str(e):
            raise HTTPException(status_code=409, detail=f"File already exists: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> None:
    await delete_game_file(db, file_id)


@router.post("/sync-files", response_model=dict)
def sync_files(
        game_id: int,
        db: Session = Depends(get_db),
        admin=Depends(get_current_admin)
) -> dict:
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    try:
        added, skipped = sync_game_files(db, game)
        return {
            "game_id": game_id,
            "added_files": added,
            "skipped_files": skipped
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@system_files_router.post("/sync-all", response_model=dict)
def full_system_sync(
        background_tasks: BackgroundTasks,
        admin=Depends(get_current_admin)
) -> dict:
    current = _read_sync_status()
    if current.get("status") == "running":
        return {
            **current,
            "detail": "Full filesystem sync is already running.",
        }

    started = {
        "status": "running",
        "detail": "Full filesystem sync is running.",
        "started_at": _utc_now(),
        "finished_at": None,
        "result": None,
        "error": None,
    }
    _write_sync_status(started)

    def _run_sync():
        try:
            with with_db() as db:
                results = sync_all_files(db)
            _write_sync_status({
                "status": "completed",
                "detail": "Full filesystem sync completed.",
                "started_at": started["started_at"],
                "finished_at": _utc_now(),
                "result": results,
                "error": None,
            })
            logger.info(f"Sync completed. Results: {results}")
        except Exception as e:
            _write_sync_status({
                "status": "failed",
                "detail": "Full filesystem sync failed.",
                "started_at": started["started_at"],
                "finished_at": _utc_now(),
                "result": None,
                "error": str(e),
            })
            logger.exception("Sync failed")

    background_tasks.add_task(_run_sync)
    return started


@system_files_router.get("/sync-all/status", response_model=dict)
def full_system_sync_status(admin=Depends(get_current_admin)) -> dict:
    return _read_sync_status()


class StorageBackendSyncRequest(BaseModel):
    source: str
    target: str


@system_files_router.post("/sync-storage", response_model=dict)
def copy_between_storage_backends(
        payload: StorageBackendSyncRequest,
        background_tasks: BackgroundTasks,
        admin=Depends(get_current_admin),
) -> dict:
    def _run_copy():
        try:
            with with_db() as db:
                results = sync_storage_backends(db, payload.source, payload.target)
            logger.info(f"Storage backend copy completed. Results: {results}")
        except Exception as e:
            logger.error(f"Storage backend copy failed: {str(e)}")

    background_tasks.add_task(_run_copy)
    return {
        "status": "started",
        "detail": f"Copying managed files from {payload.source} to {payload.target} in background.",
    }


@system_files_router.get("/categories", response_model=List[str])
def list_file_categories() -> List[str]:
    """
    Returns the list of allowed content categories as strings.
    """
    return [c.value for c in FileCategory]


@downloads_router.get("/{file_id}")
async def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    admin = Depends(get_current_admin_optional),
):
    """
    Single download endpoint:
      - If caller is admin (valid bearer token), allow unconditionally.
      - Otherwise require app_config 'public_downloads_enabled' to be truthy
        ("true" | "1" | "yes" | "on", case-insensitive).
    """
    if not admin:
        flag = (get_app_config_value(db, "public_downloads_enabled") or "").strip().lower()
        if flag not in {"true", "1", "yes", "on"}:
            raise HTTPException(status_code=403, detail="Public downloads are disabled")

    try:
        return get_downloadable_file(db, file_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

class LabelUpdate(BaseModel):
    label: constr(strip_whitespace=True, min_length=1)


@router.patch("/{file_id}/label", response_model=FileResponse)
async def patch_file_label(
    game_id: int,
    file_id: int,
    payload: LabelUpdate,
    db: Session = Depends(get_db),
    admin = Depends(get_current_admin),
) -> FileResponse:
    """
    Update a file's human-readable label.

    Request body:
        { "label": "New label" }

    Returns the updated file record.
    """
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    game_ref = str(game.igdb_id) if game.igdb_id else "".join(c for c in game.name.lower() if c.isalnum())

    try:
        updated = await update_file_label(db, file_id, game_ref, payload.label)
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")
