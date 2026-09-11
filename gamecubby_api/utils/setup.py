from sqlalchemy import text
from sqlalchemy.orm import Session
from ..models.admin import AdminUser
from ..utils.auth import hash_password
from ..models.app_config import AppConfig
from ..utils.app_config import get_app_config_value


def perform_first_run_setup(
        db: Session,
        admin_username: str,
        admin_password: str,
        igdb_client_id: str,
        igdb_client_secret: str,
        query_limit: int,
        public_downloads_enabled: bool = False,
        file_storage_backend: str = "local",
        backup_storage_backend: str = "local",
        s3_bucket: str | None = None,
        s3_region: str | None = None,
        s3_endpoint_url: str | None = None,
        s3_access_key_id: str | None = None,
        s3_secret_access_key: str | None = None,
        s3_prefix: str | None = None,
        s3_presigned_url_expires: int = 900,
) -> None:
    file_backend = (file_storage_backend or "local").strip().lower()
    backup_backend = (backup_storage_backend or "local").strip().lower()
    if file_backend not in {"local", "s3"}:
        raise ValueError("File storage backend must be local or s3")
    if backup_backend not in {"local", "s3"}:
        raise ValueError("Backup storage backend must be local or s3")

    try:
        expires = max(60, int(s3_presigned_url_expires or 900))
    except (TypeError, ValueError) as exc:
        raise ValueError("S3 presigned URL expiry must be a number") from exc

    values = {
        "CLIENT_ID": igdb_client_id,
        "CLIENT_SECRET": igdb_client_secret,
        "QUERY_LIMIT": str(query_limit),
        "public_downloads_enabled": "true" if public_downloads_enabled else "false",
        "file_storage_backend": file_backend,
        "backup_storage_backend": backup_backend,
        "s3_bucket": (s3_bucket or "").strip(),
        "s3_region": (s3_region or "").strip(),
        "s3_endpoint_url": (s3_endpoint_url or "").strip(),
        "s3_access_key_id": (s3_access_key_id or "").strip(),
        "s3_secret_access_key": (s3_secret_access_key or "").strip(),
        "s3_prefix": (s3_prefix or "").strip().strip("/"),
        "s3_presigned_url_expires": str(expires),
        "is_firstrun_done": "true",
    }

    try:
        # A transaction-scoped lock makes the status check and initial writes one operation.
        db.execute(text("SELECT pg_advisory_xact_lock(918220145)"))
        if get_app_config_value(db, "is_firstrun_done") == "true":
            raise ValueError("Setup already completed")
        if db.query(AdminUser.id).first():
            raise ValueError("Admin user already exists")

        db.add(AdminUser(username=admin_username, password_hash=hash_password(admin_password)))
        for key, value in values.items():
            db.add(AppConfig(key=key, value=value))
        db.commit()
    except Exception:
        db.rollback()
        raise


def is_first_run_done(db: Session) -> bool:
    """
    Returns True if initial setup has been completed, otherwise False.
    Treat any non-'true' value (including None) as False.
    """
    value = get_app_config_value(db, "is_firstrun_done")
    return (value or "").lower() == "true"
