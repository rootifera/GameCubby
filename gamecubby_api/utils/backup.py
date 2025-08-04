import os
import subprocess
import tempfile
import shutil

from fastapi.responses import StreamingResponse
from urllib.parse import urlparse
from pathlib import Path
from fastapi import UploadFile
from datetime import datetime
from ..db import DATABASE_URL

BACKUP_DIR = Path("storage/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def create_backup() -> StreamingResponse:
    parsed = urlparse(DATABASE_URL)

    db_user = parsed.username
    db_password = parsed.password
    db_host = parsed.hostname or "localhost"
    db_port = str(parsed.port or 5432)
    db_name = parsed.path.lstrip("/")

    if not all([db_user, db_password, db_name]):
        raise RuntimeError("Incomplete database connection details")

    pgpass_content = f"{db_host}:{db_port}:{db_name}:{db_user}:{db_password}"
    tmp_dir = tempfile.mkdtemp()
    pgpass_path = os.path.join(tmp_dir, ".pgpass")

    with open(pgpass_path, "w") as f:
        f.write(pgpass_content + "\n")
    os.chmod(pgpass_path, 0o600)

    timestamp = datetime.now().strftime("%d%m%Y-%H%M%S")
    backup_filename = f"gamecubby-db-{timestamp}.dump"
    backup_path = os.path.join(tmp_dir, backup_filename)

    try:
        subprocess.run(
            [
                "pg_dump",
                "-Fc",
                "-h", db_host,
                "-p", db_port,
                "-U", db_user,
                "-f", backup_path,
                db_name,
            ],
            check=True,
            env={**os.environ, "PGPASSFILE": pgpass_path},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        shutil.rmtree(tmp_dir)
        raise RuntimeError(f"pg_dump failed: {e.stderr.decode().strip()}")

    def file_iterator():
        with open(backup_path, "rb") as f:
            yield from f
        shutil.rmtree(tmp_dir)

    return StreamingResponse(
        file_iterator(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename={backup_filename}"
        }
    )
