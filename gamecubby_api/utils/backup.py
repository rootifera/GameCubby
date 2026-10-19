from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List
from sqlalchemy.engine import make_url

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import DATABASE_URL
from .app_config import get_app_config_value
from .storage import _s3_bucket, _s3_client, _s3_prefix

logger = logging.getLogger("gamecubby.backup")

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "storage/backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

LOGS_DIR = BACKUP_DIR / "logs"
PRERESTORE_DIR = BACKUP_DIR / "prerestore"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
PRERESTORE_DIR.mkdir(parents=True, exist_ok=True)


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _stamp_full(now: datetime | None = None) -> str:
    """
    Returns YYYYMMDD_HHMMSS in UTC by default.
    """
    now = now or _now_utc()
    return now.strftime("%Y%m%d_%H%M%S")

def _manual_filename(now: datetime | None = None) -> str:
    """
    Manual/download filename (requested):
      backup_gamecubby_YYYYMMDD_HHMMSS.dump
    """
    return f"backup_gamecubby_{_stamp_full(now)}.dump"

def _auto_filename(now: datetime | None = None) -> str:
    """
    Auto-backup filename (requested):
      auto_gamecubby_YYYYMMDD_HHMMSS.dump
    """
    return f"auto_gamecubby_{_stamp_full(now)}.dump"


CHECKSUM_SUFFIX = ".sha256"


def _checksum_path(path: Path) -> Path:
    return path.with_name(path.name + CHECKSUM_SUFFIX)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_checksum(path: Path) -> Path:
    """
    Write `<file>.sha256` next to a finished backup, in `sha256sum` format.
    The restore step verifies it before touching the database.
    """
    sidecar = _checksum_path(path)
    tmp = sidecar.with_name(sidecar.name + ".tmp")
    tmp.write_text(f"{_sha256_file(path)}  {path.name}\n", encoding="utf-8")
    os.replace(tmp, sidecar)
    return sidecar


STATUS_FILE = BACKUP_DIR / "last_backup.json"


def read_backup_status() -> dict | None:
    """Result of the most recent backup attempt (None if there has been none)."""
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _record_backup_result(ok: bool, *, uri: str | None = None, error: str | None = None) -> None:
    """
    Persist the outcome of a backup so failures are visible (API + UI) instead of
    only living in a log line. Never raises: bookkeeping must not fail a backup.
    """
    try:
        previous = read_backup_status() or {}
        failures = 0 if ok else int(previous.get("consecutive_failures") or 0) + 1
        record = {
            "ok": ok,
            "at": _now_utc().isoformat(),
            "uri": uri,
            "error": error,
            "consecutive_failures": failures,
            "last_success_at": _now_utc().isoformat() if ok else previous.get("last_success_at"),
        }
        tmp = STATUS_FILE.with_name(STATUS_FILE.name + ".tmp")
        tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.replace(tmp, STATUS_FILE)
    except Exception:
        logger.warning("could not record backup status", exc_info=True)


@dataclass
class SavedBackup:
    uri: str
    size: int
    local_path: Path | None = None



def _pg_dump_to(backup_path: Path) -> None:
    """
    Execute pg_dump -Fc to the given absolute file path.
    Uses a temporary PGPASSFILE so the password isn’t exposed on argv.
    """
    parsed = make_url(DATABASE_URL)

    db_user = parsed.username
    db_password = parsed.password
    db_host = parsed.host or "localhost"
    db_port = str(parsed.port or 5432)
    db_name = parsed.database

    if not all([db_user, db_password, db_name]):
        raise RuntimeError("Incomplete database connection details")

    tmp_dir = tempfile.mkdtemp()
    pgpass_path = os.path.join(tmp_dir, ".pgpass")
    partial_path = backup_path.with_name(backup_path.name + ".partial")

    try:
        with open(pgpass_path, "w", encoding="utf-8") as f:
            f.write(f"{db_host}:{db_port}:{db_name}:{db_user}:{db_password}\n")
        os.chmod(pgpass_path, 0o600)

        backup_path.parent.mkdir(parents=True, exist_ok=True)
        # Dump to a temp name and rename only on success, so a crash mid-dump
        # never leaves a truncated file that looks like a backup.

        proc = subprocess.run(
            [
                "pg_dump",
                "-Fc",
                "-h", db_host,
                "-p", db_port,
                "-U", db_user,
                "-f", str(partial_path),
                db_name,
            ],
            check=True,
            env={**os.environ, "PGPASSFILE": pgpass_path},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            raise RuntimeError("pg_dump failed with non-zero exit.")
        os.replace(partial_path, backup_path)
        _write_checksum(backup_path)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pg_dump failed: {e.stderr.decode(errors='ignore').strip()}")
    finally:
        try:
            partial_path.unlink(missing_ok=True)
        except Exception:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)


def create_backup() -> StreamingResponse:
    """
    Creates a one-off pg_dump in a temp file and streams it to the client.
    (Manual backup via GET /backup/)

    Filename format (updated as requested):
      backup_gamecubby_YYYYMMDD_HHMMSS.dump
    """
    tmp_dir = tempfile.mkdtemp()
    try:
        backup_filename = _manual_filename()
        backup_path = Path(tmp_dir) / backup_filename

        _pg_dump_to(backup_path)

        def file_iterator():
            # Fixed-size chunks (iterating a binary file splits at arbitrary newline
            # bytes), and always remove the temp dump -- even if the client disconnects
            # mid-download and this generator is closed early.
            try:
                with open(backup_path, "rb") as f:
                    while chunk := f.read(1024 * 1024):
                        yield chunk
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        return StreamingResponse(
            file_iterator(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={backup_filename}"},
        )
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _config_value(db: Session, key: str, default: str = "") -> str:
    value = get_app_config_value(db, key)
    return (value if value is not None else default).strip()


def _backup_storage_backend(db: Session) -> str:
    backend = _config_value(db, "backup_storage_backend", "local").lower()
    if backend not in {"local", "s3"}:
        backend = "local"
    return backend


def _backup_s3_key(db: Session, filename: str) -> str:
    prefix = _s3_prefix(db)
    key = f"backups/{filename}"
    return f"{prefix}/{key}" if prefix else key


def _backup_s3_prefix(db: Session) -> str:
    prefix = _s3_prefix(db)
    return f"{prefix}/backups/" if prefix else "backups/"


def _is_backup_name(name: str) -> bool:
    return name.endswith((".dump", ".backup", ".pgc", ".pgdump", ".tar", ".pgcustom"))


def list_backups(db: Session, warnings: list[str] | None = None) -> list[dict]:
    """
    List local and S3 backups. If S3 is the active backend and listing it fails,
    the reason is appended to `warnings` (and logged) rather than silently making
    it look like there are no S3 backups.
    """
    backups: list[dict] = []

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for path in BACKUP_DIR.iterdir():
        if not path.is_file() or not _is_backup_name(path.name):
            continue
        try:
            st = path.stat()
        except Exception:
            continue
        backups.append({
            "name": path.name,
            "relpath": path.name,
            "abspath": str(path),
            "uri": str(path),
            "source": "local",
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        })

    try:
        bucket = _s3_bucket(db)
        prefix = _backup_s3_prefix(db)
        client = _s3_client(db)
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj.get("Key")
                if not key or key.endswith("/"):
                    continue
                name = key.split("/")[-1]
                if not _is_backup_name(name):
                    continue
                last_modified = obj.get("LastModified")
                backups.append({
                    "name": name,
                    "relpath": key,
                    "abspath": f"s3://{bucket}/{key}",
                    "uri": f"s3://{bucket}/{key}",
                    "source": "s3",
                    "size": obj.get("Size", 0),
                    "mtime": last_modified.isoformat() if last_modified else "",
                })
    except Exception as e:
        # Only a problem if S3 is actually where backups are supposed to be.
        if _backup_storage_backend(db) == "s3":
            logger.warning("could not list S3 backups: %s", e)
            if warnings is not None:
                warnings.append(f"Could not list S3 backups: {getattr(e, 'detail', None) or e}")

    backups.sort(key=lambda item: item.get("mtime") or "", reverse=True)
    return backups


def sync_backup_storage(db: Session, source: str, target: str) -> dict:
    source = source.strip().lower()
    target = target.strip().lower()
    if source not in {"local", "s3"} or target not in {"local", "s3"}:
        raise ValueError("source and target must be 'local' or 's3'")
    if source == target:
        raise ValueError("source and target must be different")

    bucket = _s3_bucket(db)
    result = {"source": source, "target": target, "copied": 0, "skipped": 0, "failed": 0, "errors": []}

    if source == "local" and target == "s3":
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        for path in BACKUP_DIR.iterdir():
            if not path.is_file() or not _is_backup_name(path.name):
                continue
            try:
                key = _backup_s3_key(db, path.name)
                try:
                    _s3_client(db).head_object(Bucket=bucket, Key=key)
                    result["skipped"] += 1
                    continue
                except Exception:
                    pass
                _s3_client(db).upload_file(str(path), bucket, key)
                sidecar = _checksum_path(path)
                if sidecar.exists():
                    _s3_client(db).upload_file(str(sidecar), bucket, key + CHECKSUM_SUFFIX)
                result["copied"] += 1
            except Exception as e:
                result["failed"] += 1
                result["errors"].append(f"{path.name}: {str(e)}")
        return result

    prefix = _backup_s3_prefix(db)
    client = _s3_client(db)
    paginator = client.get_paginator("list_objects_v2")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key")
            if not key or key.endswith("/"):
                continue
            name = key.split("/")[-1]
            if not _is_backup_name(name):
                continue
            try:
                target_path = BACKUP_DIR / name
                if target_path.exists():
                    result["skipped"] += 1
                    continue
                partial = target_path.with_name(target_path.name + ".partial")
                client.download_file(bucket, key, str(partial))
                os.replace(partial, target_path)
                try:
                    client.download_file(bucket, key + CHECKSUM_SUFFIX, str(_checksum_path(target_path)))
                except Exception:
                    pass  # older backups have no checksum sidecar
                result["copied"] += 1
            except Exception as e:
                result["failed"] += 1
                result["errors"].append(f"{key}: {str(e)}")

    return result


def save_backup_to_disk(db: Session) -> SavedBackup:
    """
    Create a backup in the configured storage backend and record the outcome in
    `last_backup.json` (see `read_backup_status`).
    """
    try:
        saved = _save_backup(db)
    except Exception as e:
        logger.error("backup failed: %s", e, exc_info=True)
        _record_backup_result(False, error=str(e))
        raise
    _record_backup_result(True, uri=saved.uri)
    return saved


def _save_backup(db: Session) -> SavedBackup:
    """
    Creates an *auto* backup directly under BACKUP_DIR with the requested name:
      auto_gamecubby_YYYYMMDD_HHMMSS.dump

    Returns metadata for the saved backup.
    """
    filename = _auto_filename()
    if _backup_storage_backend(db) == "s3":
        tmp_dir = tempfile.mkdtemp()
        tmp_path = Path(tmp_dir) / filename
        try:
            _pg_dump_to(tmp_path)
            size = tmp_path.stat().st_size
            bucket = _s3_bucket(db)
            key = _backup_s3_key(db, filename)
            client = _s3_client(db)
            client.upload_file(str(tmp_path), bucket, key)
            client.upload_file(str(_checksum_path(tmp_path)), bucket, key + CHECKSUM_SUFFIX)
            return SavedBackup(uri=f"s3://{bucket}/{key}", size=size, local_path=None)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    target = BACKUP_DIR / filename
    _pg_dump_to(target)
    return SavedBackup(uri=str(target), size=target.stat().st_size if target.exists() else 0, local_path=target)


def _expired(items: list[tuple[object, datetime]], cutoff: datetime, keep: int) -> list[object]:
    """
    From (item, mtime) pairs, return the items older than `cutoff` -- but never
    touch the newest `keep` items. Without this, a stretch of failing backups
    longer than the retention period would let pruning delete every good backup.
    """
    newest_first = sorted(items, key=lambda it: it[1], reverse=True)
    return [item for item, ts in newest_first[keep:] if ts < cutoff]


def prune_old_backups(db: Session, retention_days: int) -> List[str]:
    """
    Prunes old backups according to retention settings.

    Always prunes:
      - auto_gamecubby_*.dump       (auto backups created by scheduler)

    Additionally prunes when CLEAR_MANUAL_BACKUPS=yes:
      - backup_gamecubby_*.dump     (manual/download backups)
      - logs/*.log                  (backup/restore logs)
      - prerestore/*.dump           (pre-restore dumps)

    Age is determined using the file’s mtime.
    Returns a list of deleted Paths.
    """
    deleted: List[str] = []
    if retention_days <= 0:
        return deleted

    cutoff = _now_utc() - timedelta(days=retention_days)
    min_keep = max(0, _env_int("BACKUP_MIN_KEEP", 3))

    if _backup_storage_backend(db) == "s3":
        bucket = _s3_bucket(db)
        prefix = _backup_s3_key(db, "auto_gamecubby_")
        client = _s3_client(db)
        paginator = client.get_paginator("list_objects_v2")
        candidates: list[tuple[str, datetime]] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj.get("Key")
                last_modified = obj.get("LastModified")
                if not key or not key.endswith(".dump") or not key.split("/")[-1].startswith("auto_gamecubby_"):
                    continue
                if last_modified:
                    candidates.append((key, last_modified))
        for key in _expired(candidates, cutoff, min_keep):
            try:
                client.delete_object(Bucket=bucket, Key=key)
                deleted.append(f"s3://{bucket}/{key}")
                try:
                    client.delete_object(Bucket=bucket, Key=key + CHECKSUM_SUFFIX)
                except Exception:
                    pass
            except Exception:
                logger.warning("could not prune s3://%s/%s", bucket, key, exc_info=True)
        return deleted

    def _older_than_cutoff(p: Path) -> bool:
        try:
            ts = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            return ts < cutoff
        except Exception:
            return False

    def _mtime(p: Path) -> datetime | None:
        try:
            return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        except Exception:
            return None

    def _prune_dumps(pattern: str) -> None:
        dated = [(p, ts) for p in BACKUP_DIR.glob(pattern) if (ts := _mtime(p)) is not None]
        for p in _expired(dated, cutoff, min_keep):
            try:
                p.unlink(missing_ok=True)
                _checksum_path(p).unlink(missing_ok=True)
                deleted.append(str(p))
            except Exception:
                logger.warning("could not prune %s", p, exc_info=True)

    _prune_dumps("auto_gamecubby_*.dump")

    if _env_bool("CLEAR_MANUAL_BACKUPS", False):
        _prune_dumps("backup_gamecubby_*.dump")

        for p in LOGS_DIR.glob("*.log"):
            try:
                if _older_than_cutoff(p):
                    p.unlink(missing_ok=True)
                    deleted.append(str(p))
            except Exception:
                pass

        for p in PRERESTORE_DIR.glob("*.dump"):
            try:
                if _older_than_cutoff(p):
                    p.unlink(missing_ok=True)
                    deleted.append(str(p))
            except Exception:
                pass

    return deleted
