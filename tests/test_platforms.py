from fastapi.testclient import TestClient
import pytest

@pytest.fixture(scope="module")
def client():
    from conftest import get_authenticated_client
    return get_authenticated_client()


def test_get_platform_by_id(client: TestClient):
    igdb_id = 126
    resp_igdb = client.get(f"/igdb/game/{igdb_id}")
    assert resp_igdb.status_code == 200
    platforms = resp_igdb.json().get("platforms", [])
    assert platforms, "IGDB game should have platforms"

    platform_id = platforms[0]["id"]
    resp_get = client.get(f"/platforms/{platform_id}")
    assert resp_get.status_code == 200
    platform = resp_get.json()
    assert platform["id"] == platform_id
    assert isinstance(platform["name"], str)
    assert platform["name"] != ""


def test_list_platforms(client: TestClient):
    resp = client.get("/platforms/")
    assert resp.status_code == 200
    platforms = resp.json()
    assert isinstance(platforms, list)
    assert any("PC (Microsoft Windows)" in p["name"] for p in platforms)


def test_get_nonexistent_platform_returns_404(client: TestClient):
    resp = client.get("/platforms/999999")
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"] == "Platform not found"
