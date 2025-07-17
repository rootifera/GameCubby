from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, File
from sqlalchemy.orm import Session
from typing import Literal
from ..models.game import Game
from ..db import get_db
from ..utils.storage import upload_and_register_file, sanitize_filename

router = APIRouter(prefix='/games/{game_id}/files', tags=['Files'])

@router.post('/upload', response_model=dict)
async def upload_file(
    game_id: int,
    file_type: Literal['isos', 'images', 'files'] = Form(...),
    label: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
) -> dict:
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    safe_name = sanitize_filename(file.filename)

    try:
        file_record = upload_and_register_file(
            db=db,
            game=game,
            upload_file=file,
            file_type=file_type,
            label=label,
            safe_filename=safe_name
        )

        return {
            "status": "success",
            "file_id": file_record.id,
            "path": file_record.path,
            "game_ref": file_record.game
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )