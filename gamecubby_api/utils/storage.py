import re
from pathlib import Path
from typing import List, Tuple
import sqlalchemy.exc
from sqlalchemy.orm import Session
from ..models.game import Game
from ..db import get_db
import logging
from fastapi import UploadFile, HTTPException
import aiofiles
from typing import Literal
from ..models.storage import GameFile
from fastapi.responses import FileResponse
import logging
from shutil import rmtree
from ..utils.db_tools import with_db

STORAGE_ROOT = Path("./storage")
UPLOADS_DIR = STORAGE_ROOT / "uploads"


def ensure_game_folders(autocreate_all=False) -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    if autocreate_all:
        with with_db() as db:
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


async def upload_and_register_file(
        db: Session,
        game: Game,
        upload_file: UploadFile,
        file_type: Literal["isos", "images", "files"],
        label: str,
        safe_filename: str,
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

    if dest_path.exists():
        existing_file = db.query(GameFile).filter(GameFile.path == str(dest_path)).first()
        if existing_file:
            raise ValueError(f"File already exists at this path (ID: {existing_file.id})")

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(dest_path, 'wb') as buffer:
            while chunk := await upload_file.read(8192):
                await buffer.write(chunk)

        file_record = GameFile(
            game=game_ref,
            path=str(dest_path),
            label=label.strip()
        )
        db.add(file_record)
        db.commit()
        return file_record

    except sqlalchemy.exc.IntegrityError as e:
        if "UNIQUE constraint failed: files.path" in str(e):
            db.rollback()
            existing = db.query(GameFile).filter(GameFile.path == str(dest_path)).first()
            raise ValueError(f"File already registered (ID: {existing.id})") from e
        raise

    except Exception:
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        db.rollback()
        raise


async def delete_game_file(
        db: Session,
        file_id: int,
        game_ref: str
) -> None:
    file_record = db.get(GameFile, file_id)
    if not file_record:
        raise ValueError("File not found")

    if file_record.game != game_ref:
        raise ValueError("File does not belong to specified game")

    file_path = Path(file_record.path)

    try:
        if file_path.exists():
            file_path.unlink(missing_ok=True)

        db.delete(file_record)
        db.commit()

    except Exception as e:
        db.rollback()
        raise RuntimeError(f"Deletion failed: {str(e)}") from e


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


def sync_game_files(
        db: Session,
        game: Game,
        file_types: List[str] = ["isos", "images", "files"]
) -> Tuple[int, int]:
    game_ref = str(game.igdb_id) if game.igdb_id else \
        "".join(c for c in game.name.lower() if c.isalnum())

    base_path = Path("storage/uploads") / \
                ("igdb" if game.igdb_id else "local") / \
                game_ref

    added = 0
    skipped = 0

    for file_type in file_types:
        type_path = base_path / file_type
        if not type_path.exists():
            continue

        for file_path in type_path.iterdir():
            if file_path.is_file():
                existing = db.query(GameFile).filter(
                    GameFile.path == str(file_path)
                ).first()

                if not existing:
                    db.add(GameFile(
                        game=game_ref,
                        path=str(file_path),
                        label="File Found",
                    ))
                    added += 1
                else:
                    skipped += 1

    db.commit()
    return (added, skipped)


def sync_all_files(db: Session) -> dict:
    results = {
        "total_added": 0,
        "total_skipped": 0,
        "game_results": {}
    }

    storage_root = Path("storage/uploads")
    logging.debug(f"Starting sync_all_files in {storage_root.resolve()}")

    for platform in ["igdb", "local"]:
        platform_path = storage_root / platform
        if not platform_path.exists():
            logging.warning(f"Platform path {platform_path} does not exist, skipping.")
            continue

        for game_ref in platform_path.iterdir():
            if game_ref.is_dir():
                logging.debug(f"Processing game folder: {game_ref.name}")
                game_results = {"added": 0, "skipped": 0}

                for file_type in ["isos", "images", "files"]:
                    type_path = game_ref / file_type
                    if not type_path.exists():
                        logging.debug(f"File type folder {type_path} missing, skipping.")
                        continue

                    for file_path in type_path.iterdir():
                        if file_path.is_file():
                            existing = db.query(GameFile).filter(
                                GameFile.path == str(file_path)
                            ).first()

                            if not existing:
                                db.add(GameFile(
                                    game=game_ref.name,
                                    path=str(file_path),
                                    label="File Found"
                                ))
                                game_results["added"] += 1
                                logging.info(f"Added new file record for {file_path}")
                            else:
                                game_results["skipped"] += 1
                                logging.debug(f"Skipped existing file record {file_path}")

                results["total_added"] += game_results["added"]
                results["total_skipped"] += game_results["skipped"]
                results["game_results"][game_ref.name] = game_results

    db.commit()
    logging.info(f"Initial sync completed: {results['total_added']} files added, {results['total_skipped']} skipped.")

    db_game_refs = set()

    igdb_ids = db.query(Game.igdb_id).filter(Game.igdb_id.isnot(None), Game.igdb_id != 0).all()
    db_game_refs.update(str(row[0]) for row in igdb_ids if row[0])

    local_games = db.query(Game.name).filter(Game.igdb_id == 0).all()
    for row in local_games:
        name = row[0]
        if name:
            normalized = "".join(c for c in name.lower() if c.isalnum())
            db_game_refs.add(normalized)

    for platform in ["igdb", "local"]:
        platform_path = storage_root / platform
        if not platform_path.exists():
            continue

        for game_ref in platform_path.iterdir():
            if game_ref.is_dir():
                if game_ref.name not in db_game_refs:
                    logging.info(f"Deleting orphaned folder {game_ref}")
                    rmtree(game_ref)

                    orphan_files = db.query(GameFile).filter(GameFile.game == game_ref.name).all()
                    for f in orphan_files:
                        db.delete(f)
                    db.commit()
                    logging.info(f"Deleted {len(orphan_files)} orphaned file records from DB.")

    return results


def get_downloadable_file(db: Session, file_id: int) -> FileResponse:
    file_record = db.get(GameFile, file_id)
    if not file_record:
        raise HTTPException(404, "File record not found")

    file_path = Path(file_record.path)
    if not file_path.exists():
        raise HTTPException(404, "File not found on disk")

    return FileResponse(
        path=file_path,
        filename=file_path.name
    )
