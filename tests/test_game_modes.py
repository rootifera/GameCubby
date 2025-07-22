from fastapi.testclient import TestClient
from gamecubby_api.main import app

client = TestClient(app)

def test_modes_sync_and_basic_crud():
    resp = client.post("/modes/sync")
    assert resp.status_code in (200, 202)
    resp = client.get("/modes/")
    assert resp.status_code == 200
    modes = resp.json()
    assert len(modes) >= 1

    mode_ids = [m["id"] for m in modes[:2]]
    resp = client.post("/games/", json={
        "name": "Test Mode Game",
        "mode_ids": mode_ids
    })
    assert resp.status_code == 200
    game = resp.json()
    assert "modes" in game
    assert {m["id"] for m in game["modes"]} == set(mode_ids)

    new_mode_ids = [modes[-1]["id"]]
    resp = client.put(f"/games/{game['id']}", json={"mode_ids": new_mode_ids})
    assert resp.status_code == 200
    updated = resp.json()
    assert "modes" in updated
    assert {m["id"] for m in updated["modes"]} == set(new_mode_ids)

    resp = client.get(f"/games/{game['id']}")
    assert resp.status_code == 200
    fetched = resp.json()
    assert {m["id"] for m in fetched["modes"]} == set(new_mode_ids)

def test_game_modes_from_igdb():
    resp = client.post("/games/from_igdb", json={
        "igdb_id": 666,
        "platform_ids": [],
        "tag_ids": [],
        "location_id": None,
        "condition": 0,
        "order": 0
    })
    assert resp.status_code == 200
    game = resp.json()
    assert "modes" in game
    assert len(game["modes"]) > 0
