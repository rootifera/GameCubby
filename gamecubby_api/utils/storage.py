from pathlib import Path
from sqlalchemy.orm import Session
from ..models.game import Game
from ..db import get_db
import logging

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