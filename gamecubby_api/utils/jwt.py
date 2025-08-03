from typing import Any
from jose import jwt, JWTError
from fastapi import HTTPException
from .app_config import get_or_create_secret_key
from ..db import get_db

ALGORITHM = "HS256"


def create_access_token(payload: dict) -> str:
    db = next(get_db())
    secret_key = get_or_create_secret_key(db)
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    db = next(get_db())
    secret_key = get_or_create_secret_key(db)
    try:
        return jwt.decode(token, secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
