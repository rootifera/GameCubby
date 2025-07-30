from passlib.context import CryptContext
from ..models.admin import AdminUser
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from ..db import get_db
from ..models.admin import AdminUser
import os

security = HTTPBearer()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def ensure_default_admin(db):
    existing = db.query(AdminUser).filter_by(username="admin").first()
    if not existing:
        print("[Auth] No admin user found. Creating default admin: admin / admin")
        hashed_pw = pwd_context.hash("admin")
        user = AdminUser(username="admin", password_hash=hashed_pw)
        db.add(user)
        db.commit()


def get_current_admin(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> AdminUser:
    token = credentials.credentials
    key = str(SECRET_KEY)

    try:
        # print("[DEBUG] Token:", token[:40] + "...")
        # print("[DEBUG] SECRET_KEY type:", type(key), "value:", key)

        payload = jwt.decode(token, key, algorithms=[ALGORITHM])

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

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)
