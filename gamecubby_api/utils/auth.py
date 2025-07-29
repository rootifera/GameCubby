from passlib.context import CryptContext
from ..models.admin import AdminUser

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def ensure_default_admin(db):
    existing = db.query(AdminUser).filter_by(username="admin").first()
    if not existing:
        print("[Auth] No admin user found. Creating default admin: admin / admin")
        hashed_pw = pwd_context.hash("admin")
        user = AdminUser(username="admin", password_hash=hashed_pw)
        db.add(user)
        db.commit()