import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    from conftest import get_authenticated_client
    return get_authenticated_client()


@pytest.mark.usefixtures("client")
def test_igdb_search_returns_results(client: TestClient):
    resp = client.get("/igdb/search", params={"name": "Diablo II"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert any(game["name"] == "Diablo II" for game in data)
    for game in data:
        assert "id" in game
        assert "name" in game
        assert "cover_url" in game
        assert "platforms" in game
        assert "summary" in game


@pytest.mark.usefixtures("client")
def test_igdb_search_fields_correct(client: TestClient):
    resp = client.get("/igdb/search", params={"name": "Diablo II"})
    assert resp.status_code == 200
    games = resp.json()
    d2 = next((g for g in games if g["id"] == 126), None)
    assert d2 is not None
    assert d2["name"] == "Diablo II"
    assert isinstance(d2["cover_url"], str) and d2["cover_url"].startswith("https://")
    assert d2["release_date"] == 2000
    platform_names = [p["name"] for p in d2["platforms"]]
    assert "PC (Microsoft Windows)" in platform_names
    assert "action role-playing" in d2["summary"].lower()


@pytest.mark.usefixtures("client")
def test_igdb_game_by_id(client: TestClient):
    igdb_id = 126
    resp = client.get(f"/igdb/game/{igdb_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == igdb_id
    assert data["name"] == "Diablo II"
    assert isinstance(data["cover_url"], str) and data["cover_url"].startswith("https://")
    assert isinstance(data["release_date"], int) and data["release_date"] == 2000
    platform_names = [p["name"] for p in data["platforms"]]
    assert "PC (Microsoft Windows)" in platform_names
    assert "collection" in data
    assert data["collection"]["name"] == "Diablo"
    assert "action role-playing" in data["summary"].lower()


@pytest.mark.usefixtures("client")
def test_igdb_collection_lookup(client: TestClient):
    igdb_id = 126
    resp = client.get(f"/igdb/collection_lookup/{igdb_id}")
    assert resp.status_code == 200
    collections = resp.json()
    assert isinstance(collections, list)
    assert any(c["id"] == 24 and c["name"] == "Diablo" for c in collections)
