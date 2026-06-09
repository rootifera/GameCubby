import re
import os
from pathlib import Path
from typing import List, Tuple, Optional
import logging
import sqlalchemy.exc
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response
from shutil import rmtree
import aiofiles

from ..models.game import Game
from ..models.storage import GameFile, FileCategory
from ..utils.db_tools import with_db
from ..utils.app_config import get_app_config_value

STORAGE_ROOT = Path("./storage")
UPLOADS_DIR = STORAGE_ROOT / "uploads"


def _config_value(db: Session, key: str, default: str = "") -> str:
    value = get_app_config_value(db, key)
    return (value if value is not None else default).strip()


def configured_storage_backend(db: Session) -> str:
    backend = _config_value(db, "file_storage_backend", "local").lower()
    if backend not in {"local", "s3"}:
        raise HTTPException(500, f"Unsupported file_storage_backend: {backend}")
    return backend


def _backup_storage_backend(db: Session) -> str:
    backend = _config_value(db, "backup_storage_backend", "local").lower()
    if backend not in {"local", "s3"}:
        raise HTTPException(500, f"Unsupported backup_storage_backend: {backend}")
    return backend


def _s3_bucket(db: Session) -> str:
    bucket = _config_value(db, "s3_bucket")
    if not bucket:
        raise HTTPException(500, "s3_bucket is required when S3 storage is enabled")
    return bucket


def _s3_prefix(db: Session) -> str:
    return _config_value(db, "s3_prefix").strip("/")


def _s3_presign_expires(db: Session) -> int:
    try:
        return max(60, int(_config_value(db, "s3_presigned_url_expires", "900")))
    except ValueError:
        return 900


def _s3_client(db: Session):
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise HTTPException(500, "boto3 is required for S3 storage") from exc

    kwargs = {}
    endpoint_url = _config_value(db, "s3_endpoint_url")
    region = _config_value(db, "s3_region")
    access_key = _config_value(db, "s3_access_key_id")
    secret_key = _config_value(db, "s3_secret_access_key")

    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    if region:
        kwargs["region_name"] = region
    if access_key:
        kwargs["aws_access_key_id"] = access_key
    if secret_key:
        kwargs["aws_secret_access_key"] = secret_key

    kwargs["config"] = Config(signature_version="s3v4")
    return boto3.client("s3", **kwargs)


def _s3_key(db: Session, game: Game, category: FileCategory, filename: str) -> str:
    prefix = _s3_prefix(db)
    storage_group = "igdb" if game.igdb_id else "local"
    parts = ["uploads", storage_group, get_game_ref(game), category.value, filename]
    key = "/".join(parts)
    return f"{prefix}/{key}" if prefix else key


def _s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def _upload_size(upload_file: UploadFile) -> Optional[int]:
    size = getattr(upload_file, "size", None)
    if isinstance(size, int):
        return size

    try:
        pos = upload_file.file.tell()
        upload_file.file.seek(0, os.SEEK_END)
        end = upload_file.file.tell()
        upload_file.file.seek(pos)
        return end
    except Exception:
        return None


def _key_without_prefix(db: Session, key: str) -> str:
    prefix = _s3_prefix(db)
    if prefix and key.startswith(f"{prefix}/"):
        return key[len(prefix) + 1:]
    return key


def _category_from_key(db: Session, key: str) -> Optional[FileCategory]:
    parts = _key_without_prefix(db, key).split("/")
    if len(parts) < 5 or parts[0] != "uploads":
        return None
    try:
        return FileCategory(parts[3])
    except ValueError:
        return None


def _game_ref_from_key(db: Session, key: str) -> Optional[str]:
    parts = _key_without_prefix(db, key).split("/")
    if len(parts) < 5 or parts[0] != "uploads":
        return None
    return parts[2]


def _storage_group_from_key(db: Session, key: str) -> Optional[str]:
    parts = _key_without_prefix(db, key).split("/")
    if len(parts) < 5 or parts[0] != "uploads":
        return None
    if parts[1] not in {"igdb", "local"}:
        return None
    return parts[1]


def _storage_group_from_local_path(path: str) -> Optional[str]:
    parts = Path(path).parts
    for group in ("igdb", "local"):
        if group in parts:
            idx = parts.index(group)
            if idx > 0 and parts[idx - 1] == "uploads":
                return group
    return None


def _local_path_to_s3_key(db: Session, path: str) -> Optional[str]:
    try:
        rel = Path(path).relative_to(UPLOADS_DIR)
    except ValueError:
        return None
    key = "/".join(["uploads", *rel.parts])
    prefix = _s3_prefix(db)
    return f"{prefix}/{key}" if prefix else key


def _s3_key_to_local_path(db: Session, key: str) -> Optional[Path]:
    parts = _key_without_prefix(db, key).split("/")
    if len(parts) < 5 or parts[0] != "uploads":
        return None
    return STORAGE_ROOT.joinpath(*parts)


def _list_s3_objects(db: Session, prefix: str):
    client = _s3_client(db)
    bucket = _s3_bucket(db)
    paginator = client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key")
            if not key or key.endswith("/"):
                continue
            yield obj


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
    backend = configured_storage_backend(db)

    if backend == "s3":
        bucket = _s3_bucket(db)
        key = _s3_key(db, game, category, safe_filename)
        path = _s3_uri(bucket, key)

        existing_file = db.query(GameFile).filter(GameFile.path == path).first()
        if existing_file:
            raise HTTPException(409, f"File already exists at this path (ID: {existing_file.id})")

        try:
            upload_file.file.seek(0)
            extra_args = {}
            if upload_file.content_type:
                extra_args["ContentType"] = upload_file.content_type

            _s3_client(db).upload_fileobj(
                upload_file.file,
                bucket,
                key,
                ExtraArgs=extra_args or None,
            )

            file_record = GameFile(
                game=game_ref,
                path=path,
                label=label.strip(),
                category=category,
                storage_backend="s3",
                object_key=key,
                size=_upload_size(upload_file),
                content_type=upload_file.content_type,
            )
            db.add(file_record)
            db.commit()
            return file_record

        except sqlalchemy.exc.IntegrityError as e:
            db.rollback()
            existing = db.query(GameFile).filter(GameFile.path == path).first()
            raise HTTPException(
                409, f"File already registered (ID: {existing.id if existing else 'unknown'})"
            ) from e
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            try:
                _s3_client(db).delete_object(Bucket=bucket, Key=key)
            except Exception:
                pass
            raise HTTPException(500, f"S3 upload failed: {str(e)}") from e

    dest_path = UPLOADS_DIR / ("igdb" if game.igdb_id else "local") / game_ref / category.value / safe_filename

    if dest_path.exists():
        existing_file = db.query(GameFile).filter(GameFile.path == str(dest_path)).first()
        if existing_file:
            raise HTTPException(409, f"File already exists at this path (ID: {existing_file.id})")

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        size = 0
        async with aiofiles.open(dest_path, "wb") as buffer:
            while chunk := await upload_file.read(8192):
                size += len(chunk)
                await buffer.write(chunk)

        file_record = GameFile(
            game=game_ref,
            path=str(dest_path),
            label=label.strip(),
            category=category,
            storage_backend="local",
            size=size,
            content_type=upload_file.content_type,
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
) -> None:
    file_record = db.get(GameFile, file_id)
    if not file_record:
        raise HTTPException(404, "File not found")

    backend = file_record.storage_backend or "local"

    try:
        if backend == "s3":
            key = file_record.object_key
            path_value = file_record.path or ""
            if not key and path_value.startswith("s3://"):
                key = path_value.split("/", 3)[3]
            if key:
                _s3_client(db).delete_object(Bucket=_s3_bucket(db), Key=key)
        else:
            file_path = Path(file_record.path)
            if file_path.is_file():
                file_path.unlink()

        db.delete(file_record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Deletion failed: {str(e)}") from e


async def update_file_label(
        db: Session,
        file_id: int,
        game_ref: str,
        new_label: str
) -> GameFile:
    """
    Update the human-readable label for a stored file.
    Validations:
      - file exists
      - belongs to the specified game_ref
      - new_label is non-empty after strip()
    """
    file_record = db.get(GameFile, file_id)
    if not file_record:
        raise HTTPException(404, "File not found")

    if file_record.game != game_ref:
        raise HTTPException(400, "File does not belong to specified game")

    if not new_label or not new_label.strip():
        raise HTTPException(400, "Label cannot be empty")

    try:
        file_record.label = new_label.strip()
        db.add(file_record)
        db.commit()
        db.refresh(file_record)
        return file_record
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Update failed: {str(e)}") from e


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


def sync_storage_backends(db: Session, source: str, target: str) -> dict:
    source = source.strip().lower()
    target = target.strip().lower()
    if source not in {"local", "s3"} or target not in {"local", "s3"}:
        raise HTTPException(400, "source and target must be 'local' or 's3'")
    if source == target:
        raise HTTPException(400, "source and target must be different")
    if "s3" in {source, target}:
        _s3_bucket(db)

    result = {"source": source, "target": target, "copied": 0, "skipped": 0, "failed": 0, "errors": []}
    records = db.query(GameFile).filter(GameFile.storage_backend == source).all()

    for record in records:
        try:
            if source == "local" and target == "s3":
                local_path = Path(record.path or "")
                if not local_path.is_file():
                    result["failed"] += 1
                    result["errors"].append(f"Missing local file for row {record.id}: {record.path}")
                    continue

                key = _local_path_to_s3_key(db, str(local_path))
                if not key:
                    result["failed"] += 1
                    result["errors"].append(f"Local path outside uploads tree for row {record.id}: {record.path}")
                    continue

                bucket = _s3_bucket(db)
                target_path = _s3_uri(bucket, key)
                if db.query(GameFile).filter(GameFile.path == target_path).first():
                    result["skipped"] += 1
                    continue

                extra_args = {}
                if record.content_type:
                    extra_args["ContentType"] = record.content_type
                _s3_client(db).upload_file(
                    str(local_path),
                    bucket,
                    key,
                    ExtraArgs=extra_args or None,
                )

                db.add(GameFile(
                    game=record.game,
                    path=target_path,
                    label=record.label,
                    category=record.category,
                    storage_backend="s3",
                    object_key=key,
                    size=local_path.stat().st_size,
                    content_type=record.content_type,
                ))
                result["copied"] += 1

            elif source == "s3" and target == "local":
                key = record.object_key
                path_value = record.path or ""
                if not key and path_value.startswith("s3://"):
                    key = path_value.split("/", 3)[3]
                if not key:
                    result["failed"] += 1
                    result["errors"].append(f"Missing S3 object key for row {record.id}")
                    continue

                local_path = _s3_key_to_local_path(db, key)
                if not local_path:
                    result["failed"] += 1
                    result["errors"].append(f"S3 key is outside managed layout for row {record.id}: {key}")
                    continue

                target_path = str(local_path)
                if db.query(GameFile).filter(GameFile.path == target_path).first():
                    result["skipped"] += 1
                    continue

                local_path.parent.mkdir(parents=True, exist_ok=True)
                _s3_client(db).download_file(_s3_bucket(db), key, str(local_path))

                db.add(GameFile(
                    game=record.game,
                    path=target_path,
                    label=record.label,
                    category=record.category,
                    storage_backend="local",
                    object_key=None,
                    size=local_path.stat().st_size,
                    content_type=record.content_type,
                ))
                result["copied"] += 1
        except Exception as e:
            result["failed"] += 1
            result["errors"].append(f"Row {record.id}: {str(e)}")

    db.commit()
    return result


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
    if configured_storage_backend(db) == "s3":
        bucket = _s3_bucket(db)
        prefix = _s3_key(db, game, FileCategory.other, "").rsplit("/", 2)[0] + "/"
        added = 0
        skipped = 0
        wanted = set(categories or list(FileCategory))

        for obj in _list_s3_objects(db, prefix):
            key = obj["Key"]
            cat = _category_from_key(db, key)
            if cat is None or cat not in wanted:
                continue
            path = _s3_uri(bucket, key)
            existing = db.query(GameFile).filter(GameFile.path == path).first()
            if existing:
                skipped += 1
                continue
            db.add(GameFile(
                game=game_ref,
                path=path,
                label=Path(key).name,
                category=cat,
                storage_backend="s3",
                object_key=key,
                size=obj.get("Size"),
            ))
            added += 1

        db.commit()
        return added, skipped

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
                        storage_backend="local",
                        size=file_path.stat().st_size,
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
    if configured_storage_backend(db) == "s3":
        bucket = _s3_bucket(db)
        prefix = f"{_s3_prefix(db)}/uploads/" if _s3_prefix(db) else "uploads/"

        for obj in _list_s3_objects(db, prefix):
            key = obj["Key"]
            cat = _category_from_key(db, key)
            game_ref = _game_ref_from_key(db, key)
            if cat is None or not game_ref:
                continue

            game_results = results["game_results"].setdefault(game_ref, {"added": 0, "skipped": 0})
            path = _s3_uri(bucket, key)
            existing = db.query(GameFile).filter(GameFile.path == path).first()
            if existing:
                game_results["skipped"] += 1
                results["total_skipped"] += 1
                continue

            db.add(GameFile(
                game=game_ref,
                path=path,
                label=Path(key).name,
                category=cat,
                storage_backend="s3",
                object_key=key,
                size=obj.get("Size"),
            ))
            game_results["added"] += 1
            results["total_added"] += 1

        db.commit()
        logging.info(f"S3 sync completed: {results['total_added']} files added, {results['total_skipped']} skipped.")
        return results

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
                                storage_backend="local",
                                size=file_path.stat().st_size,
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


def get_downloadable_file(db: Session, file_id: int) -> Response:
    file_record = db.get(GameFile, file_id)
    if not file_record:
        raise HTTPException(404, "File record not found")

    backend = file_record.storage_backend or "local"
    if backend == "s3":
        key = file_record.object_key
        path_value = file_record.path or ""
        if not key and path_value.startswith("s3://"):
            key = path_value.split("/", 3)[3]
        if not key:
            raise HTTPException(404, "S3 object key not found")

        filename = Path(key).name.replace('"', "_").replace("\\", "_")
        try:
            url = _s3_client(db).generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": _s3_bucket(db),
                    "Key": key,
                    "ResponseContentDisposition": f'attachment; filename="{filename}"',
                },
                ExpiresIn=_s3_presign_expires(db),
            )
        except Exception as e:
            raise HTTPException(500, f"Could not create S3 download URL: {str(e)}") from e

        return RedirectResponse(url=url, status_code=307)

    file_path = Path(file_record.path)
    if not file_path.exists():
        raise HTTPException(404, "File not found on disk")

    return FileResponse(
        path=file_path,
        filename=file_path.name
    )
