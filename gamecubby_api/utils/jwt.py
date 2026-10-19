from typing import Any
from jose import jwt, JWTError
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .app_config import get_or_create_secret_key
from .db_tools import with_db

ALGORITHM = "HS256"


def _secret_key(db: Session | None) -> str:
    """
    Read the signing secret. Pass the caller's own session whenever there is one:
    opening a second session here costs an extra pool connection (plus a pre-ping)
    on every authenticated request -- and while the caller's session already holds a
    connection (e.g. login, during bcrypt), a second one can exhaust the pool under load.
    """
    if db is not None:
        return get_or_create_secret_key(db)
    with with_db() as own_db:
        return get_or_create_secret_key(own_db)


def create_access_token(payload: dict, db: Session | None = None) -> str:
    return jwt.encode(payload, _secret_key(db), algorithm=ALGORITHM)


def decode_access_token(token: str, db: Session | None = None) -> dict[str, Any]:
    secret_key = _secret_key(db)
    try:
        return jwt.decode(token, secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
