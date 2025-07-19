from fastapi.testclient import TestClient
from gamecubby_api.main import app

client = TestClient(app)

def test_list_platforms():
    resp_igdb = client.get("/igdb/game/126")
    assert resp_igdb.status_code == 200
    game = resp_igdb.json()
    assert "platforms" in game and game["platforms"]

    resp = client.get("/platforms/")
    assert resp.status_code == 200
    platforms = resp.json()
    assert isinstance(platforms, list)
    expected_names = [p["name"] for p in game["platforms"]]
    assert any(p["name"] in expected_names for p in platforms)


def test_get_platform_by_id():
    resp_igdb = client.get("/igdb/game/126")
    assert resp_igdb.status_code == 200
    game = resp_igdb.json()
    platform = game["platforms"][0]
    platform_id = platform["id"]

    resp = client.get(f"/platforms/{platform_id}")
    assert resp.status_code == 200
    platform_got = resp.json()
    assert platform_got["id"] == platform_id
    assert platform_got["name"] == platform["name"]
