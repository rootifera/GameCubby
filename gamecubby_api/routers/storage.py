from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, File
from sqlalchemy.orm import Session
from typing import Literal
from ..models.game import Game
from ..db import get_db
from typing import List
from ..models.storage import GameFile
from ..schemas.storage import FileResponse
from ..utils.storage import upload_and_register_file, sanitize_filename, delete_game_file

router = APIRouter(prefix='/games/{game_id}/files', tags=['Files'])

@router.get('/', response_model=List[FileResponse])
def list_files(
    game_id: int,
    db: Session = Depends(get_db)
) -> List[FileResponse]:
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    game_ref = str(game.igdb_id) if game.igdb_id else \
        "".join(c for c in game.name.lower() if c.isalnum())

    files = db.query(GameFile).filter(GameFile.game == game_ref).all()
    return files


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
        file_record = await upload_and_register_file(
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
        if "already exists" in str(e) or "already registered" in str(e):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "file_exists",
                    "message": str(e),
                    "suggested_action": "Use a different filename or manage the existing file"
                }
            )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )

@router.delete('/{file_id}', status_code=204)
async def delete_file(
    game_id: int,
    file_id: int,
    db: Session = Depends(get_db)
) -> None:

    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    game_ref = str(game.igdb_id) if game.igdb_id else \
        "".join(c for c in game.name.lower() if c.isalnum())

    try:
        await delete_game_file(db, file_id, game_ref)
    except ValueError as e:
        raise HTTPException(
            status_code=404 if "not found" in str(e).lower() else 400,
            detail=str(e)
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))