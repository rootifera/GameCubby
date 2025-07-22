from fastapi.testclient import TestClient
from gamecubby_api.main import app

client = TestClient(app)

def test_genres_sync_and_list():
    resp_sync = client.post("/genres/sync")
    assert resp_sync.status_code == 200 or resp_sync.status_code == 201

    resp = client.get("/genres/")
    assert resp.status_code == 200
    genres = resp.json()
    assert isinstance(genres, list)
    assert any("id" in g and "name" in g for g in genres)
    assert len(genres) > 0

def test_get_genre_by_id():
    resp = client.get("/genres/")
    assert resp.status_code == 200
    genres = resp.json()
    assert len(genres) > 0
    genre = genres[0]

    resp_single = client.get(f"/genres/{genre['id']}")
    assert resp_single.status_code == 200
    single = resp_single.json()
    assert single["id"] == genre["id"]
    assert single["name"] == genre["name"]
