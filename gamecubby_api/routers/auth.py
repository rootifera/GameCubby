from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext

from ..db import get_db
from ..schemas.admin import LoginRequest, PasswordChangeRequest
from ..utils.auth import get_current_admin
from ..models.admin import AdminUser
from ..utils.jwt import create_access_token
from ..models.auth import PasswordChangeRequest

router = APIRouter(prefix="/auth", tags=["Authentication"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/login")
def login(request: LoginRequest):
    db_gen = get_db()
    db: Session = next(db_gen)
    try:
        user = db.query(AdminUser).filter_by(username=request.username).first()
        if not user or not pwd_context.verify(request.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": "admin",
            "exp": datetime.now(timezone.utc) + timedelta(hours=24)
        }

        token = create_access_token(payload)
        return {
            "access_token": token,
            "token_type": "bearer"
        }
    finally:
        db_gen.close()


@router.post("/change-password")
def change_password(
    data: PasswordChangeRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Change the admin's password.
    - Verifies current password against stored hash.
    - Enforces minimum length of 6 characters for new password (via Pydantic model).
    - On success, hashes and persists the new password.
    """
    if not pwd_context.verify(data.current_password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect current password")

    admin.password_hash = pwd_context.hash(data.new_password)
    db.add(admin)
    db.commit()

    return {"message": "Password changed successfully."}
