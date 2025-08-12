from typing import Optional

from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..models.admin import AdminUser
from ..db import get_db
from .jwt import decode_access_token

security = HTTPBearer()

security_optional = HTTPBearer(auto_error=False)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_current_admin(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> AdminUser:
    token = credentials.credentials
    payload = decode_access_token(token)

    user_id = payload.get("sub")
    role = payload.get("role")

    if role != "admin":
        raise HTTPException(status_code=403, detail="Not an admin")

    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user ID")

    user = db.query(AdminUser).filter_by(id=int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

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
        payload = decode_access_token(token)
    except Exception:
        return None

    user_id = payload.get("sub")
    role = payload.get("role")
    if role != "admin" or not user_id:
        return None

    user = db.query(AdminUser).filter_by(id=int(user_id)).first()
    return user


def hash_password(password: str) -> str:
    return pwd_context.hash(password)
