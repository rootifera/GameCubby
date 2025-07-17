import re
import unicodedata
from pathlib import Path
from sqlalchemy.orm import Session
from ..models.game import Game
from ..db import get_db
import logging
from fastapi import UploadFile
import shutil
from typing import Literal
from ..models.storage import GameFile


STORAGE_ROOT = Path("./storage")
UPLOADS_DIR = STORAGE_ROOT / "uploads"


def ensure_game_folders(autocreate_all=False) -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    if autocreate_all:
        db = next(get_db())
        try:
            games = db.query(Game).all()
            for game in games:
                _create_single_game_folders(db, game)
            logging.info(f"Ensured folders for {len(games)} games")
        except Exception as e:
            logging.error(f"Folder creation failed: {e}")
            raise


def _create_single_game_folders(db: Session, game: Game) -> str:
    base_path = UPLOADS_DIR / f"igdb/{game.igdb_id}" if game.igdb_id else \
        UPLOADS_DIR / f"local/{''.join(c for c in game.name.lower() if c.isalnum())}"

    for folder in ["isos", "images", "files"]:
        (base_path / folder).mkdir(parents=True, exist_ok=True)

    return str(base_path)


def upload_and_register_file(
        db: Session,
        game: Game,
        upload_file: UploadFile,
        file_type: Literal["isos", "images", "files"],
        label: str,
        safe_filename: str,  # New parameter
        **kwargs
) -> GameFile:
    if not label.strip():
        raise ValueError("Label cannot be empty")
    if file_type not in {"isos", "images", "files"}:
        raise ValueError(f"Invalid file type: {file_type}")

    game_ref = str(game.igdb_id) if game.igdb_id else \
        "".join(c for c in game.name.lower() if c.isalnum())

    dest_path = Path("storage/uploads") / \
                ("igdb" if game.igdb_id else "local") / \
                game_ref / file_type / safe_filename

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        with dest_path.open("wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)

        file_record = GameFile(
            game=game_ref,
            path=str(dest_path),
            label=label.strip()
        )
        db.add(file_record)
        db.commit()
        return file_record

    except Exception:
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        db.rollback()
        raise


def sanitize_filename(filename: str) -> str:

    clean_name = Path(filename).name

    stem, suffix = Path(clean_name).stem, Path(clean_name).suffix

    if stem:
        first_char = stem[0] if stem[0].isalnum() else '_'
        rest = re.sub(r'[^\w.-]', '_', stem[1:])
        clean_stem = first_char + rest
    else:
        clean_stem = '_'

    return f"{clean_stem}{suffix}"[:255]