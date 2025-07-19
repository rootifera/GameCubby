from fastapi.testclient import TestClient
from gamecubby_api.main import app

client = TestClient(app)

def test_read_root():
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app_name"] == "GameCubby API"
    assert data["version"] == "0.1"
    assert data["build_name"] == "Three-headed monkey"
    assert isinstance(data["build_time"], int)
