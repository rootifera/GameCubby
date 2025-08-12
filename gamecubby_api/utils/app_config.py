from sqlalchemy.orm import Session
from typing import Optional, List
import secrets
from ..models.app_config import AppConfig


def set_app_config_value(db: Session, key: str, value: str) -> AppConfig:
    entry = db.query(AppConfig).filter_by(key=key).first()
    if entry:
        entry.value = value
    else:
        entry = AppConfig(key=key, value=value)
        db.add(entry)
    db.commit()
    return entry


def get_app_config_value(db: Session, key: str) -> Optional[str]:
    entry = db.query(AppConfig).filter_by(key=key).first()
    return entry.value if entry else None


def delete_app_config_key(db: Session, key: str) -> bool:
    entry = db.query(AppConfig).filter_by(key=key).first()
    if not entry:
        return False
    db.delete(entry)
    db.commit()
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
    generated = secrets.token_urlsafe(64)
    set_app_config_value(db, key, generated)
    return generated

def get_or_create_query_limit(db: Session, default: int = 50) -> int:
    key = "QUERY_LIMIT"
    value = get_app_config_value(db, key)
    try:
        return int(value)
    except (TypeError, ValueError):
        set_app_config_value(db, key, str(default))
        return default