from fastapi.testclient import TestClient
from gamecubby_api.main import app

client = TestClient(app)

def test_refresh_single_metadata():
    igdb_id = 126
    resp_igdb = client.get(f"/igdb/game/{igdb_id}")
    assert resp_igdb.status_code == 200
    igdb_game = resp_igdb.json()
    platform_ids = [p["id"] for p in igdb_game.get("platforms", [])]

    data = {
        "igdb_id": igdb_id,
        "platform_ids": platform_ids,
        "location_id": None,
        "tag_ids": [],
        "condition": 1,
        "order": 0
    }
    resp = client.post("/games/from_igdb", json=data)
    assert resp.status_code == 200
    game = resp.json()
    game_id = game["id"]

    resp_refresh = client.post(f"/games/{game_id}/refresh_metadata")
    assert resp_refresh.status_code == 200
    assert "game" in resp_refresh.json() or "id" in resp_refresh.json()


def test_refresh_all_metadata():
    resp = client.post("/games/refresh_all_metadata")
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"

def test_force_refresh_metadata():
    resp = client.post("/games/force_refresh_metadata")
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"
