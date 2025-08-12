import re
from pathlib import Path
from typing import List, Tuple, Optional
import logging
import sqlalchemy.exc
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
from fastapi.responses import FileResponse
from shutil import rmtree
import aiofiles

from ..models.game import Game
from ..models.storage import GameFile, FileCategory
from ..utils.db_tools import with_db

STORAGE_ROOT = Path("./storage")
UPLOADS_DIR = STORAGE_ROOT / "uploads"


def get_game_ref(game: Game) -> str:
    return str(game.igdb_id) if game.igdb_id else "".join(c for c in game.name.lower() if c.isalnum())


def ensure_game_folders(autocreate_all: bool = False) -> None:
    """
    Ensure the base uploads directory exists. If autocreate_all is True,
    create category subfolders for every game in the DB.
    Layout:
        ./storage/uploads/{igdb|local}/{game_ref}/{category}/
    """
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
    """
    Create the per-game category folders under uploads.
    """
    base_path = (
        UPLOADS_DIR / f"igdb/{game.igdb_id}"
        if game.igdb_id
        else UPLOADS_DIR / f"local/{''.join(c for c in game.name.lower() if c.isalnum())}"
    )

    for cat in FileCategory:
        (base_path / cat.value).mkdir(parents=True, exist_ok=True)

    return str(base_path)


async def upload_and_register_file(
        db: Session,
        game: Game,
        upload_file: UploadFile,
        label: str,
        safe_filename: str,
        *,
        category: FileCategory,
) -> GameFile:
    """
    Store the uploaded file on disk and create a DB record with a *content category*.

    Layout on disk:
        ./storage/uploads/{igdb|local}/{game_ref}/{category}/{safe_filename}

    Notes:
    - `category` is REQUIRED (FileCategory).
    - `safe_filename` should already be sanitized by the caller.
    """
    if not label or not label.strip():
        raise HTTPException(400, "Label cannot be empty")

    game_ref = get_game_ref(game)
    dest_path = UPLOADS_DIR / ("igdb" if game.igdb_id else "local") / game_ref / category.value / safe_filename

    if dest_path.exists():
        existing_file = db.query(GameFile).filter(GameFile.path == str(dest_path)).first()
        if existing_file:
            raise HTTPException(409, f"File already exists at this path (ID: {existing_file.id})")

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(dest_path, "wb") as buffer:
            while chunk := await upload_file.read(8192):
                await buffer.write(chunk)

        file_record = GameFile(
            game=game_ref,
            path=str(dest_path),
            label=label.strip(),
            category=category,
        )
        db.add(file_record)
        db.commit()
        return file_record

    except sqlalchemy.exc.IntegrityError as e:
        db.rollback()
        existing = db.query(GameFile).filter(GameFile.path == str(dest_path)).first()
        raise HTTPException(
            409, f"File already registered (ID: {existing.id if existing else 'unknown'})"
        ) from e

    except Exception as e:
        db.rollback()
        try:
            dest_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(500, f"File upload failed: {str(e)}") from e


async def delete_game_file(
        db: Session,
        file_id: int,
        game_ref: str
) -> None:
    file_record = db.get(GameFile, file_id)
    if not file_record:
        raise HTTPException(404, "File not found")

    if file_record.game != game_ref:
        raise HTTPException(400, "File does not belong to specified game")

    file_path = Path(file_record.path)

    try:
        if file_path.exists():
            file_path.unlink(missing_ok=True)

        db.delete(file_record)
        db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Deletion failed: {str(e)}") from e


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
        categories: Optional[List[FileCategory]] = None
) -> Tuple[int, int]:
    """
    Scan the on-disk storage for this game and register any files missing in DB.
    Uses *content categories* as subfolders:
        ./storage/uploads/{igdb|local}/{game_ref}/{category}/<files>

    Returns:
        (added, skipped)
    """
    game_ref = get_game_ref(game)
    base_path = UPLOADS_DIR / ("igdb" if game.igdb_id else "local") / game_ref

    added = 0
    skipped = 0

    cats = categories or list(FileCategory)

    for cat in cats:
        type_path = base_path / cat.value
        if not type_path.exists():
            continue

        for file_path in type_path.iterdir():
            if file_path.is_file():
                existing = db.query(GameFile).filter(GameFile.path == str(file_path)).first()

                if not existing:
                    db.add(GameFile(
                        game=game_ref,
                        path=str(file_path),
                        label="File Found",
                        category=cat,
                    ))
                    added += 1
                else:
                    skipped += 1

    db.commit()
    return added, skipped


def sync_all_files(db: Session) -> dict:
    """
    Scan the whole storage tree and register any files missing in DB.
    Uses content-category folders:
        ./storage/uploads/{igdb|local}/{game_ref}/{category}/<files>
    Also removes orphaned game folders that no longer exist in DB.
    """
    results = {"total_added": 0, "total_skipped": 0, "game_results": {}}

    storage_root = UPLOADS_DIR
    logging.debug(f"Starting sync_all_files in {storage_root.resolve()}")

    for platform in ["igdb", "local"]:
        platform_path = storage_root / platform
        if not platform_path.exists():
            logging.warning(f"Platform path {platform_path} does not exist, skipping.")
            continue

        for game_ref in platform_path.iterdir():
            if not game_ref.is_dir():
                continue

            logging.debug(f"Processing game folder: {game_ref.name}")
            game_results = {"added": 0, "skipped": 0}

            for cat in FileCategory:
                type_path = game_ref / cat.value
                if not type_path.exists():
                    continue

                for file_path in type_path.iterdir():
                    if file_path.is_file():
                        existing = db.query(GameFile).filter(GameFile.path == str(file_path)).first()
                        if not existing:
                            db.add(GameFile(
                                game=game_ref.name,
                                path=str(file_path),
                                label="File Found",
                                category=cat,
                            ))
                            game_results["added"] += 1
                            logging.info(f"Added new file record for {file_path}")
                        else:
                            game_results["skipped"] += 1

            results["total_added"] += game_results["added"]
            results["total_skipped"] += game_results["skipped"]
            results["game_results"][game_ref.name] = game_results

    db.commit()
    logging.info(f"Initial sync completed: {results['total_added']} files added, {results['total_skipped']} skipped.")

    # --- Orphan cleanup (delete game folders with no corresponding DB game) ---
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

        for game_dir in platform_path.iterdir():
            if game_dir.is_dir() and game_dir.name not in db_game_refs:
                logging.info(f"Deleting orphaned folder {game_dir}")
                rmtree(game_dir)

                orphan_files = db.query(GameFile).filter(GameFile.game == game_dir.name).all()
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
