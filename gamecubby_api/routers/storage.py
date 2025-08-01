from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, Form, File
from sqlalchemy.orm import Session
from typing import List, Literal
from ..db import get_db
from ..models.game import Game
from ..models.storage import GameFile
from ..schemas.storage import FileResponse
from ..utils.storage import (
    upload_and_register_file, sanitize_filename, delete_game_file,
    sync_game_files, sync_all_files, get_downloadable_file
)
from ..utils.auth import get_current_admin

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/games/{game_id}/files', tags=['Files'])
system_files_router = APIRouter(prefix='/files', tags=['Scan All Files'])
downloads_router = APIRouter(prefix='/downloads', tags=['Downloads'])


@router.get('/', response_model=List[FileResponse])
def list_files(game_id: int, db: Session = Depends(get_db)) -> List[FileResponse]:
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    game_ref = str(game.igdb_id) if game.igdb_id else "".join(c for c in game.name.lower() if c.isalnum())
    files = db.query(GameFile).filter(GameFile.game == game_ref).all()
    return files


@router.post('/upload', response_model=dict)
async def upload_file(
        game_id: int,
        file_type: Literal['isos', 'images', 'files'] = Form(...),
        label: str = Form(...),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        admin=Depends(get_current_admin)
) -> dict:
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    safe_name = sanitize_filename(file.filename)

    try:
        file_record = await upload_and_register_file(
            db=db, game=game, upload_file=file,
            file_type=file_type, label=label, safe_filename=safe_name
        )
        return {
            "file_id": file_record.id,
            "path": file_record.path,
            "game_ref": file_record.game
        }
    except ValueError as e:
        if "already exists" in str(e) or "already registered" in str(e):
            raise HTTPException(status_code=409, detail=f"File already exists: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete('/{file_id}', status_code=204)
async def delete_file(
        game_id: int,
        file_id: int,
        db: Session = Depends(get_db),
        admin=Depends(get_current_admin)
) -> None:
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    game_ref = str(game.igdb_id) if game.igdb_id else "".join(c for c in game.name.lower() if c.isalnum())

    try:
        await delete_game_file(db, file_id, game_ref)
    except ValueError as e:
        raise HTTPException(
            status_code=404 if "not found" in str(e).lower() else 400,
            detail=str(e)
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@downloads_router.get("/{file_id}")
async def download_file(file_id: int, db: Session = Depends(get_db)) -> FileResponse:
    try:
        return get_downloadable_file(db, file_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
