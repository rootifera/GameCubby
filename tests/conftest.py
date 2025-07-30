import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gamecubby_api.main import app

def get_authenticated_client() -> TestClient:
    client = TestClient(app)

    login_data = {
        "username": os.getenv("ADMIN_USER"),
        "password": os.getenv("ADMIN_PASSWORD"),
    }
    resp = client.post("/auth/login", json=login_data)
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    # Set auth header
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client

@pytest.fixture(scope="module")
def client():
    return get_authenticated_client()
