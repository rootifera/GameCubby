from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List
from urllib.parse import urlparse

from fastapi.responses import StreamingResponse

from ..db import DATABASE_URL

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



def _pg_dump_to(backup_path: Path) -> None:
    """
    Execute pg_dump -Fc to the given absolute file path.
    Uses a temporary PGPASSFILE so the password isn’t exposed on argv.
    """
    parsed = urlparse(DATABASE_URL)

    db_user = parsed.username
    db_password = parsed.password
    db_host = parsed.hostname or "localhost"
    db_port = str(parsed.port or 5432)
    db_name = parsed.path.lstrip("/")

    if not all([db_user, db_password, db_name]):
        raise RuntimeError("Incomplete database connection details")

    tmp_dir = tempfile.mkdtemp()
    pgpass_path = os.path.join(tmp_dir, ".pgpass")

    try:
        with open(pgpass_path, "w", encoding="utf-8") as f:
            f.write(f"{db_host}:{db_port}:{db_name}:{db_user}:{db_password}\n")
        os.chmod(pgpass_path, 0o600)

        backup_path.parent.mkdir(parents=True, exist_ok=True)

        proc = subprocess.run(
            [
                "pg_dump",
                "-Fc",
                "-h", db_host,
                "-p", db_port,
                "-U", db_user,
                "-f", str(backup_path),
                db_name,
            ],
            check=True,
            env={**os.environ, "PGPASSFILE": pgpass_path},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            raise RuntimeError("pg_dump failed with non-zero exit.")
    except subprocess.CalledProcessError as e:
        try:
            if backup_path.exists():
                backup_path.unlink()
        except Exception:
            pass
        raise RuntimeError(f"pg_dump failed: {e.stderr.decode(errors='ignore').strip()}")
    finally:
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
            with open(backup_path, "rb") as f:
                yield from f
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return StreamingResponse(
            file_iterator(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={backup_filename}"},
        )
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def save_backup_to_disk() -> Path:
    """
    Creates an *auto* backup directly under BACKUP_DIR with the requested name:
      auto_gamecubby_YYYYMMDD_HHMMSS.dump

    Returns the Path to the saved file.
    """
    target = BACKUP_DIR / _auto_filename()
    _pg_dump_to(target)
    return target


def prune_old_backups(retention_days: int) -> List[Path]:
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
    deleted: List[Path] = []
    if retention_days <= 0:
        return deleted

    cutoff = _now_utc() - timedelta(days=retention_days)

    def _older_than_cutoff(p: Path) -> bool:
        try:
            ts = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            return ts < cutoff
        except Exception:
            return False

    for p in BACKUP_DIR.glob("auto_gamecubby_*.dump"):
        try:
            if _older_than_cutoff(p):
                p.unlink(missing_ok=True)
                deleted.append(p)
        except Exception:
            pass

    if _env_bool("CLEAR_MANUAL_BACKUPS", False):
        for p in BACKUP_DIR.glob("backup_gamecubby_*.dump"):
            try:
                if _older_than_cutoff(p):
                    p.unlink(missing_ok=True)
                    deleted.append(p)
            except Exception:
                pass


        for p in LOGS_DIR.glob("*.log"):
            try:
                if _older_than_cutoff(p):
                    p.unlink(missing_ok=True)
                    deleted.append(p)
            except Exception:
                pass

        for p in PRERESTORE_DIR.glob("*.dump"):
            try:
                if _older_than_cutoff(p):
                    p.unlink(missing_ok=True)
                    deleted.append(p)
            except Exception:
                pass

    return deleted
