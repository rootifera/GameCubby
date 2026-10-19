import re
import os
import uuid
import asyncio
from pathlib import Path
from typing import List, Tuple, Optional
from urllib.parse import urlparse
import logging
import sqlalchemy.exc
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response
from shutil import rmtree
import aiofiles
import httpx

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


def _s3_presign_base_url(db: Session) -> str:
    """
    Optional external URL used as the endpoint when generating presigned download
    links. Useful when s3_endpoint_url points to an internal address but presigned
    download links must be reachable by external clients.
    Set s3_presigned_base_url to the public-facing endpoint (e.g. https://s3.example.com).
    The URL is used as the boto3 endpoint_url when signing, so the Host in the
    canonical request matches the host the client will actually connect to.
    """
    value = _config_value(db, "s3_presigned_base_url").rstrip("/")
    if value:
        parsed = urlparse(value)
        if not parsed.netloc:
            logging.warning(
                "s3_presigned_base_url %r appears malformed (missing scheme?); ignoring",
                value,
            )
            return ""
    return value


def _s3_client(db: Session, *, endpoint_url_override: str | None = None):
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise HTTPException(500, "boto3 is required for S3 storage") from exc

    kwargs = {}
    endpoint_url = endpoint_url_override if endpoint_url_override is not None else _config_value(db, "s3_endpoint_url")
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

    kwargs["config"] = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
    )
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

        key_existed: bool | None = None
        try:
            upload_file.file.seek(0)
            extra_args = {}
            if upload_file.content_type:
                extra_args["ContentType"] = upload_file.content_type

            # boto3 is blocking and uploads can be gigabytes (ISOs): run it in a worker
            # thread so the event loop (every other request) keeps serving. The client
            # is created here because it reads config through this DB session.
            s3 = _s3_client(db)
            # Remember whether something was already at this key (an unregistered, orphaned
            # object): if the upload then fails, that older object must not be deleted.
            key_existed = await asyncio.to_thread(_s3_object_exists, s3, bucket, key)
            await asyncio.to_thread(
                s3.upload_fileobj,
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
            if key_existed is False:  # unknown (None) or pre-existing: leave it alone
                try:
                    _s3_client(db).delete_object(Bucket=bucket, Key=key)
                except Exception:
                    pass
            raise HTTPException(500, f"S3 upload failed: {str(e)}") from e

    dest_path = UPLOADS_DIR / ("igdb" if game.igdb_id else "local") / game_ref / category.value / safe_filename

    existed_before = dest_path.exists()
    if existed_before:
        existing_file = db.query(GameFile).filter(GameFile.path == str(dest_path)).first()
        if existing_file:
            raise HTTPException(409, f"File already exists at this path (ID: {existing_file.id})")

    # Stream into a temp file next to the destination and move it into place only once
    # complete. Writing straight to dest_path meant a failed or interrupted upload both
    # left a truncated file and, in the cleanup, deleted whatever was there before.
    tmp_path = dest_path.with_name(f".{dest_path.name}.{uuid.uuid4().hex[:8]}.part")
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        size = 0
        async with aiofiles.open(tmp_path, "wb") as buffer:
            while chunk := await upload_file.read(8192):
                size += len(chunk)
                await buffer.write(chunk)
        os.replace(tmp_path, dest_path)

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
        if not existed_before:  # only remove what this upload created
            try:
                dest_path.unlink(missing_ok=True)
            except Exception:
                pass
        raise HTTPException(500, f"File upload failed: {str(e)}") from e

    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


async def delete_game_file(
        db: Session,
        file_id: int,
) -> None:
    """
    Delete a file record and its stored file.

    The database row goes first and is committed before the stored file is removed. The
    other order could delete the file and then fail to commit, leaving a record that
    points at nothing. Failing after the commit leaves at worst an unreferenced file,
    which is harmless (and is reported by the file sync).
    """
    file_record = db.get(GameFile, file_id)
    if not file_record:
        raise HTTPException(404, "File not found")

    backend = file_record.storage_backend or "local"
    s3_key = None
    local_path = None
    if backend == "s3":
        s3_key = file_record.object_key
        path_value = file_record.path or ""
        if not s3_key and path_value.startswith("s3://"):
            s3_key = path_value.split("/", 3)[3]
    else:
        local_path = Path(file_record.path)

    try:
        s3 = _s3_client(db) if s3_key else None
        bucket = _s3_bucket(db) if s3_key else None
        db.delete(file_record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Deletion failed: {str(e)}") from e

    try:
        if s3_key:
            await asyncio.to_thread(s3.delete_object, Bucket=bucket, Key=s3_key)
        elif local_path is not None and local_path.is_file():
            local_path.unlink()
    except Exception:
        _log.warning("File record %s was deleted but its stored file could not be removed", file_id, exc_info=True)


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


def sync_all_files(db: Session, *, delete_orphans: bool = False) -> dict:
    """
    Scan the whole storage tree and register any files missing in DB.
    Uses content-category folders:
        ./storage/uploads/{igdb|local}/{game_ref}/{category}/<files>
    Reports orphaned game folders that no longer exist in DB. Deletion is opt-in.
    """
    results = {"total_added": 0, "total_skipped": 0, "game_results": {}, "orphan_folders": []}
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
                results["orphan_folders"].append(str(game_dir))
                if delete_orphans:
                    logging.info("Deleting orphaned folder %s", game_dir)
                    rmtree(game_dir)
                    orphan_files = db.query(GameFile).filter(GameFile.game == game_dir.name).all()
                    for file_record in orphan_files:
                        db.delete(file_record)
                    db.commit()
                    logging.info("Deleted %s orphaned file records from DB.", len(orphan_files))

    return results


# ---------------------------------------------------------------------------
# Cover image caching
# ---------------------------------------------------------------------------

_COVER_FILENAME = "cover.jpg"
_MAX_COVER_BYTES = 10 * 1024 * 1024  # 10 MB
_log = logging.getLogger(__name__)


def _cover_local_path(game: Game) -> Path:
    group = "igdb" if game.igdb_id else "local"
    return UPLOADS_DIR / group / get_game_ref(game) / "metadata" / _COVER_FILENAME


def _cover_s3_key_for(db: Session, group: str, ref: str) -> str:
    """S3 key of a cover given its folder group ("igdb"/"local") and game ref."""
    prefix = _s3_prefix(db)
    key = f"uploads/{group}/{ref}/metadata/{_COVER_FILENAME}"
    return f"{prefix}/{key}" if prefix else key


def _s3_game_prefix(db: Session, group: str, ref: str) -> str:
    """S3 'folder' holding all of one game ref's files (always ends with '/')."""
    prefix = _s3_prefix(db)
    base = f"uploads/{group}/{ref}/"
    return f"{prefix}/{base}" if prefix else base


def _cover_s3_key(db: Session, game: Game) -> str:
    return _cover_s3_key_for(db, "igdb" if game.igdb_id else "local", get_game_ref(game))


def _write_cover_local(game: Game, data: bytes) -> None:
    path = _cover_local_path(game)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _write_cover_s3(db: Session, game: Game, data: bytes) -> None:
    _s3_client(db).put_object(
        Bucket=_s3_bucket(db),
        Key=_cover_s3_key(db, game),
        Body=data,
        ContentType="image/jpeg",
    )


async def _store_cover_bytes(db: Session, game: Game, data: bytes) -> None:
    """Write cover bytes to the configured storage without blocking the event loop."""
    if configured_storage_backend(db) == "s3":
        # Resolve everything that needs the DB session first; only the network call runs in a thread.
        client = _s3_client(db)
        bucket = _s3_bucket(db)
        key = _cover_s3_key(db, game)
        await asyncio.to_thread(client.put_object, Bucket=bucket, Key=key, Body=data, ContentType="image/jpeg")
    else:
        await asyncio.to_thread(_write_cover_local, game, data)


async def _download_cover_bytes(url: str) -> bytes | None:
    """Fetch image bytes from a URL; return None on any error."""
    try:
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "GameCubby/1.0 cover-cache"},
        ) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        data = resp.content
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/") or not data or len(data) > _MAX_COVER_BYTES:
            _log.warning("Rejected cover download from %s: content_type=%s size=%d", url, content_type, len(data))
            return None
        return data
    except httpx.HTTPStatusError as exc:
        _log.warning("Cover download failed: HTTP %s for %s", exc.response.status_code, url)
        return None
    except Exception:
        _log.warning("Cover download failed unexpectedly for %s", url, exc_info=True)
        return None


async def download_and_store_cover(db: Session, game: Game) -> bool:
    """
    Download the IGDB cover URL for *game* and write it to the configured storage.
    Returns True on success, False on any failure (download or storage error).
    Does NOT touch the database — callers set game.cover_cached.
    """
    if not game.cover_url:
        return False
    data = await _download_cover_bytes(game.cover_url)
    if data is None:
        return False
    try:
        await _store_cover_bytes(db, game, data)
        return True
    except Exception:
        _log.warning("Storage write failed for game %s cover; trying local fallback", game.id, exc_info=True)
        try:
            await asyncio.to_thread(_write_cover_local, game, data)
            return True
        except Exception:
            _log.error("Local fallback also failed for game %s cover", game.id, exc_info=True)
            return False


def store_custom_cover(db: Session, game: Game, data: bytes) -> None:
    """
    Persist user-uploaded cover bytes for a custom (non-IGDB) game.
    Raises HTTPException on storage error.
    Does NOT touch the database — callers set game.cover_cached.
    """
    try:
        if configured_storage_backend(db) == "s3":
            _write_cover_s3(db, game, data)
        else:
            _write_cover_local(game, data)
    except Exception as exc:
        raise HTTPException(500, f"Cover upload failed: {exc}") from exc


def remove_cached_cover(db: Session, game: Game) -> None:
    """
    Delete the cached cover from storage (both S3 and local if present).
    Does NOT touch the database — callers set game.cover_cached = False.
    """
    if configured_storage_backend(db) == "s3":
        try:
            _s3_client(db).delete_object(Bucket=_s3_bucket(db), Key=_cover_s3_key(db, game))
        except Exception:
            _log.warning("S3 delete failed for game %s cover; will still clear local", game.id, exc_info=True)
    path = _cover_local_path(game)
    if path.is_file():
        path.unlink()


async def serve_game_cover(db: Session, game: Game) -> Response:
    """
    Return an HTTP response for the game's cover image.
    - cover_cached=True → serve from configured storage (presigned redirect or FileResponse)
    - cover_cached=False + cover_url → 307 redirect to IGDB
    - neither                        → 404
    """
    if game.cover_cached:
        backend = configured_storage_backend(db)
        if backend == "s3":
            try:
                key = _cover_s3_key(db, game)
                presign_base = _s3_presign_base_url(db)
                presign_client = _s3_client(db, endpoint_url_override=presign_base or None)
                url = presign_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": _s3_bucket(db), "Key": key},
                    ExpiresIn=_s3_presign_expires(db),
                )
                return RedirectResponse(url=url, status_code=307)
            except Exception:
                _log.warning("S3 presign failed for game %s cover; falling back to local", game.id, exc_info=True)
        path = _cover_local_path(game)
        if path.is_file():
            return FileResponse(str(path), media_type="image/jpeg")
        _log.warning("cover_cached=True for game %s but no file found; falling back", game.id)

    if game.cover_url:
        return RedirectResponse(url=game.cover_url, status_code=307)

    raise HTTPException(404, "No cover image available for this game")


_COVER_SYNC_CONCURRENCY = 10


def _s3_object_exists(client, bucket: str, key: str) -> bool | None:
    """
    True/False if S3 gives a definite answer, None if it can't tell.
    Anything other than a clean "not found" (network error, 403, ...) is None so a
    flaky connection or missing ListBucket permission never looks like "deleted".
    """
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception as exc:
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        _log.warning("Could not verify cover object %s: %s", key, exc)
        return None


async def _covers_exist(db: Session, games: list[Game]) -> dict[int, bool | None]:
    """
    Check that each game's cached cover really exists in the configured storage
    (S3 object or local file). The `cover_cached` flag alone can go stale, e.g. when
    files are deleted from the bucket or the storage backend is switched.
    Maps game id -> True / False / None (None = could not be determined).
    """
    if configured_storage_backend(db) != "s3":
        return {g.id: _cover_local_path(g).is_file() for g in games}

    # Resolve everything that needs the DB session up front; only the S3 calls run in threads.
    client = _s3_client(db)
    bucket = _s3_bucket(db)
    keys = {g.id: _cover_s3_key(db, g) for g in games}
    semaphore = asyncio.Semaphore(_COVER_SYNC_CONCURRENCY)

    async def _check(game_id: int) -> tuple[int, bool | None]:
        async with semaphore:
            return game_id, await asyncio.to_thread(_s3_object_exists, client, bucket, keys[game_id])

    return dict(await asyncio.gather(*[_check(gid) for gid in keys]))


async def cached_cover_exists(db: Session, game: Game) -> bool | None:
    """True/False if the game's cached cover is/isn't in storage, None if unknown."""
    return (await _covers_exist(db, [game]))[game.id]


async def sync_all_game_covers(db: Session) -> dict:
    """
    Make the cover cache match reality.

    - Games without a cached cover get their IGDB cover downloaded.
    - Games flagged as cached are verified against the configured storage; if the
      file is gone the flag is cleared and the cover is downloaded again. When that
      isn't possible (no IGDB URL, e.g. a lost custom upload, or the download fails)
      the flag stays cleared so the game falls back to IGDB / shows as needing a cover.
    - If existence can't be determined (S3 error), the game is left untouched.

    Downloads run concurrently (up to _COVER_SYNC_CONCURRENCY at a time).
    Returns statistics: total, cached (downloaded this run), already_cached (verified
    present), missing_in_storage (flag was set but file was gone), unverified,
    unverified_game_ids, failed, failed_game_ids.
    """
    games = (
        db.query(Game)
        .filter(or_(and_(Game.cover_url.isnot(None), Game.cover_url != ""), Game.cover_cached.is_(True)))
        .all()
    )
    result: dict = {
        "total": len(games),
        "cached": 0,
        "already_cached": 0,
        "missing_in_storage": 0,
        "unverified": 0,
        "unverified_game_ids": [],
        "failed": 0,
        "failed_game_ids": [],
    }

    flagged = [g for g in games if g.cover_cached]
    exists = await _covers_exist(db, flagged) if flagged else {}
    stale = [g for g in flagged if exists.get(g.id) is False]
    unverified = [g for g in flagged if exists.get(g.id) is None]
    stale_ids = {g.id for g in stale}

    result["already_cached"] = len(flagged) - len(stale) - len(unverified)
    result["missing_in_storage"] = len(stale)
    result["unverified"] = len(unverified)
    result["unverified_game_ids"] = [g.id for g in unverified]

    to_process = [g for g in games if not g.cover_cached] + stale

    semaphore = asyncio.Semaphore(_COVER_SYNC_CONCURRENCY)

    async def _fetch_one(game: Game) -> tuple[Game, bool]:
        async with semaphore:
            return game, await download_and_store_cover(db, game)

    outcomes = await asyncio.gather(*[_fetch_one(g) for g in to_process])

    for game, success in outcomes:
        if success:
            game.cover_cached = True
            result["cached"] += 1
        else:
            if game.id in stale_ids:
                game.cover_cached = False  # the flag was wrong; don't keep claiming a cover
            result["failed"] += 1
            result["failed_game_ids"].append(game.id)

    db.commit()
    return result


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
            presign_base = _s3_presign_base_url(db)
            presign_client = _s3_client(db, endpoint_url_override=presign_base or None)
            url = presign_client.generate_presigned_url(
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
