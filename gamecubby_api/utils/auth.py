import hashlib
import hmac
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..models.admin import AdminUser
from ..db import get_db
from .jwt import decode_access_token

security = HTTPBearer()

security_optional = HTTPBearer(auto_error=False)

# bcrypt only looks at the first 72 bytes of a password. passlib silently truncated longer
# ones; bcrypt >= 5 raises instead. Truncating here keeps existing hashes (and long
# passwords) working exactly as before.
_BCRYPT_MAX_BYTES = 72


def password_fingerprint(password_hash: str) -> str:
    """
    Short fingerprint of an admin's password hash, stored in every login token (`pwv` claim).
    Changing the password changes the hash, so every token issued before the change stops
    working -- including one forged with a leaked SECRET_KEY, which cannot know the fingerprint
    of the new hash.
    """
    return hashlib.sha256((password_hash or "").encode("utf-8")).hexdigest()[:16]


def _token_matches_password(payload: dict, user: AdminUser) -> bool:
    claimed = str(payload.get("pwv") or "")
    return hmac.compare_digest(claimed, password_fingerprint(user.password_hash))


def get_current_admin(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> AdminUser:
    token = credentials.credentials
    payload = decode_access_token(token, db)

    user_id = payload.get("sub")
    role = payload.get("role")

    if role != "admin":
        raise HTTPException(status_code=403, detail="Not an admin")

    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user ID")

    user = db.query(AdminUser).filter_by(id=int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not _token_matches_password(payload, user):
        raise HTTPException(status_code=401, detail="Session is no longer valid, please log in again")

    return user


def get_current_admin_optional(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
        db: Session = Depends(get_db)
) -> Optional[AdminUser]:
    """
    Return the AdminUser if a valid admin bearer token is provided; otherwise None.
    Never raises for missing/invalid/unauthorized tokens (so routes can fall back to public behavior).
    """
    if not credentials:
        return None

    token = credentials.credentials
    try:
        payload = decode_access_token(token, db)
    except Exception:
        return None

    user_id = payload.get("sub")
    role = payload.get("role")
    if role != "admin" or not user_id:
        return None

    user = db.query(AdminUser).filter_by(id=int(user_id)).first()
    if user is None or not _token_matches_password(payload, user):
        return None
    return user


def _bcrypt_input(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """True only when `password` matches `password_hash`; a malformed hash is just a mismatch."""
    try:
        return bcrypt.checkpw(_bcrypt_input(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
