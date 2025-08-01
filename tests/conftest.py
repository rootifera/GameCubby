from dotenv import load_dotenv

load_dotenv()

import os
import sys
import pytest
from gamecubby_api.db import SessionLocal
from gamecubby_api.utils.auth import hash_password
from gamecubby_api.models.admin import AdminUser
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gamecubby_api.main import app


@pytest.fixture(scope="session", autouse=True)
def create_default_admin():
    db = SessionLocal()
    user = db.query(AdminUser).filter_by(username="admin").first()
    if not user:
        db.add(AdminUser(
            username="admin",
            password_hash=hash_password("admin")
        ))
        db.commit()
    db.close()


def get_authenticated_client() -> TestClient:
    client = TestClient(app)

    login_data = {
        "username": os.getenv("ADMIN_USER"),
        "password": os.getenv("ADMIN_PASSWORD"),
    }
    assert login_data["username"] and login_data["password"], "Missing login credentials from environment"

    resp = client.post("/auth/login", json=login_data)
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture(scope="module")
def client():
    return get_authenticated_client()
