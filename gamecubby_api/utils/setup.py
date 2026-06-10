from sqlalchemy.orm import Session
from ..models.admin import AdminUser
from ..utils.auth import hash_password
from ..utils.app_config import get_app_config_value, set_app_config_value


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
    if get_app_config_value(db, "is_firstrun_done") == "true":
        raise ValueError("Setup already completed")

    existing = db.query(AdminUser).filter_by(username=admin_username).first()
    if existing:
        raise ValueError("Admin user already exists")

    hashed_pw = hash_password(admin_password)
    db.add(AdminUser(username=admin_username, password_hash=hashed_pw))

    set_app_config_value(db, "CLIENT_ID", igdb_client_id)
    set_app_config_value(db, "CLIENT_SECRET", igdb_client_secret)
    set_app_config_value(db, "QUERY_LIMIT", str(query_limit))

    set_app_config_value(
        db,
        "public_downloads_enabled",
        "true" if public_downloads_enabled else "false",
    )

    file_backend = (file_storage_backend or "local").strip().lower()
    backup_backend = (backup_storage_backend or "local").strip().lower()
    if file_backend not in {"local", "s3"}:
        raise ValueError("File storage backend must be local or s3")
    if backup_backend not in {"local", "s3"}:
        raise ValueError("Backup storage backend must be local or s3")

    set_app_config_value(db, "file_storage_backend", file_backend)
    set_app_config_value(db, "backup_storage_backend", backup_backend)
    set_app_config_value(db, "s3_bucket", (s3_bucket or "").strip())
    set_app_config_value(db, "s3_region", (s3_region or "").strip())
    set_app_config_value(db, "s3_endpoint_url", (s3_endpoint_url or "").strip())
    set_app_config_value(db, "s3_access_key_id", (s3_access_key_id or "").strip())
    set_app_config_value(db, "s3_secret_access_key", (s3_secret_access_key or "").strip())
    set_app_config_value(db, "s3_prefix", (s3_prefix or "").strip().strip("/"))
    set_app_config_value(db, "s3_presigned_url_expires", str(max(60, int(s3_presigned_url_expires or 900))))

    set_app_config_value(db, "is_firstrun_done", "true")

    db.commit()


def is_first_run_done(db: Session) -> bool:
    """
    Returns True if initial setup has been completed, otherwise False.
    Treat any non-'true' value (including None) as False.
    """
    value = get_app_config_value(db, "is_firstrun_done")
    return (value or "").lower() == "true"
