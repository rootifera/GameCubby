import time
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from typing import Optional, List
import secrets
from ..models.app_config import AppConfig

# Hot, rarely-changing settings (storage backend, S3 endpoint/keys, ...) are read on every
# cover/download request -- about 11 queries per cover before this cache. A short per-process
# TTL removes almost all of them. It is cleared whenever settings change in this process; the
# other API worker catches up within the TTL. Security-critical values (SECRET_KEY) never use it.
_CONFIG_TTL_SECONDS = 10.0
_config_cache: "dict[str, tuple[float, Optional[str]]]" = {}


def invalidate_app_config_cache() -> None:
    _config_cache.clear()


def set_app_config_value(db: Session, key: str, value: str) -> AppConfig:
    entry = db.query(AppConfig).filter_by(key=key).first()
    if entry:
        entry.value = value
    else:
        entry = AppConfig(key=key, value=value)
        db.add(entry)
    db.commit()
    invalidate_app_config_cache()
    return entry


def get_app_config_value(db: Session, key: str) -> Optional[str]:
    entry = db.query(AppConfig).filter_by(key=key).first()
    return entry.value if entry else None


def get_app_config_value_cached(db: Session, key: str) -> Optional[str]:
    """`get_app_config_value` with a short per-process cache. For hot, non-sensitive settings only."""
    now = time.monotonic()
    hit = _config_cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    value = get_app_config_value(db, key)
    _config_cache[key] = (now + _CONFIG_TTL_SECONDS, value)
    return value


def delete_app_config_key(db: Session, key: str) -> bool:
    entry = db.query(AppConfig).filter_by(key=key).first()
    if not entry:
        return False
    db.delete(entry)
    db.commit()
    invalidate_app_config_cache()
    return True

def get_int_config_value(db: Session, key: str, default: int) -> int:
    value = get_app_config_value(db, key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def list_all_app_config(db: Session) -> List[AppConfig]:
    return db.query(AppConfig).order_by(AppConfig.key).all()


def get_or_create_secret_key(db: Session) -> str:
    key = "SECRET_KEY"
    value = get_app_config_value(db, key)
    if value:
        return value

    # Multiple API workers can reach first-use token validation concurrently on
    # a fresh database. Use PostgreSQL's conflict handling so exactly one worker
    # creates the key and every worker returns the persisted winner.
    generated = secrets.token_urlsafe(64)
    stmt = (
        insert(AppConfig)
        .values(key=key, value=generated)
        .on_conflict_do_nothing(index_elements=[AppConfig.key])
        .returning(AppConfig.value)
    )
    inserted = db.execute(stmt).scalar_one_or_none()
    db.commit()
    if inserted:
        return inserted

    value = get_app_config_value(db, key)
    if not value:
        raise RuntimeError("SECRET_KEY could not be created or loaded")
    return value

def get_or_create_query_limit(db: Session, default: int = 50) -> int:
    key = "QUERY_LIMIT"
    value = get_app_config_value(db, key)
    try:
        return int(value)
    except (TypeError, ValueError):
        set_app_config_value(db, key, str(default))
        return default
