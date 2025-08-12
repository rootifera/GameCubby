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

    set_app_config_value(db, "is_firstrun_done", "true")

    db.commit()


def is_first_run_done(db: Session) -> bool:
    """
    Returns True if initial setup has been completed, otherwise False.
    Treat any non-'true' value (including None) as False.
    """
    value = get_app_config_value(db, "is_firstrun_done")
    return (value or "").lower() == "true"
