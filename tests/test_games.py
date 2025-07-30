from fastapi.testclient import TestClient

def test_create_and_get_manual_game(client: TestClient):
    resp = client.post("/games/", json={
        "name": "Test Game",
        "summary": "Test Summary",
        "release_date": 2024,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": 1,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0
    })
    assert resp.status_code == 200
    game = resp.json()
    game_id = game["id"]

    resp_get = client.get(f"/games/{game_id}")
    assert resp_get.status_code == 200
    got = resp_get.json()
    assert got["id"] == game_id
    assert got["name"] == "Test Game"

def test_create_game_from_igdb(client: TestClient):
    igdb_id = 262186
    resp_meta = client.get(f"/igdb/game/{igdb_id}")
    assert resp_meta.status_code == 200
    meta = resp_meta.json()
    platform_ids = [p["id"] for p in meta.get("platforms", [])]

    resp_create = client.post("/games/from_igdb", json={
        "igdb_id": igdb_id,
        "platform_ids": platform_ids,
        "location_id": None,
        "tag_ids": [],
        "condition": 1,
        "order": 0
    })
    assert resp_create.status_code == 200
    game = resp_create.json()
    assert game["igdb_id"] == igdb_id

def test_list_games(client: TestClient):
    resp = client.get("/games/")
    assert resp.status_code == 200
    games = resp.json()
    assert isinstance(games, list)

def test_update_game(client: TestClient):
    resp_create = client.post("/games/", json={
        "name": "Updatable Game",
        "summary": "Original Summary",
        "release_date": 2000,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": 1,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0
    })
    assert resp_create.status_code == 200
    game = resp_create.json()
    game_id = game["id"]

    resp_update = client.put(f"/games/{game_id}", json={
        "name": "Updated Game"
    })
    assert resp_update.status_code == 200
    updated = resp_update.json()
    assert updated["name"] == "Updated Game"

def test_delete_game(client: TestClient):
    resp_create = client.post("/games/", json={
        "name": "Delete Me",
        "summary": "Will be deleted",
        "release_date": 1999,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": 2,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0
    })
    assert resp_create.status_code == 200
    game = resp_create.json()
    game_id = game["id"]

    resp_delete = client.delete(f"/games/{game_id}")
    assert resp_delete.status_code == 200
    assert resp_delete.json() is True

    resp_check = client.get(f"/games/{game_id}")
    assert resp_check.status_code == 404
