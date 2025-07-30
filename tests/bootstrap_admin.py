import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gamecubby_api.db import SessionLocal
from gamecubby_api.models.admin import AdminUser
from gamecubby_api.utils.auth import hash_password


def bootstrap_admin():
    db = SessionLocal()
    try:
        existing = db.query(AdminUser).filter_by(username="admin").first()
        if existing:
            print("[Bootstrap] Admin user already exists.")
            return
        print("[Bootstrap] Creating default admin user.")
        user = AdminUser(
            username="admin",
            password_hash=hash_password("admin")
        )
        db.add(user)
        db.commit()
        print("[Bootstrap] Admin user created: admin / admin")
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap_admin()
