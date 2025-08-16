from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, Form, File, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, constr

from ..db import get_db
from ..models.game import Game
from ..models.storage import GameFile
from ..schemas.storage import FileResponse, FileCategory
from ..utils.storage import (
    upload_and_register_file, sanitize_filename, delete_game_file,
    sync_game_files, sync_all_files, get_downloadable_file, update_file_label
)
from ..utils.auth import get_current_admin, get_current_admin_optional
from ..utils.app_config import get_app_config_value

import logging

logger = logging.getLogger(__name__)

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
        db: Session = Depends(get_db),
        admin=Depends(get_current_admin)
) -> dict:
    def _run_sync():
        try:
            results = sync_all_files(db)
            logger.info(f"Sync completed. Results: {results}")
        except Exception as e:
            logger.error(f"Sync failed: {str(e)}")

    background_tasks.add_task(_run_sync)
    return {"message": "Full filesystem sync started in background."}


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
