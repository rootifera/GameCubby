import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    from conftest import get_authenticated_client
    return get_authenticated_client()

@pytest.mark.usefixtures("client")
def test_list_game_modes(client: TestClient):
    resp = client.get("/modes/")
    assert resp.status_code == 200
    modes = resp.json()
    assert isinstance(modes, list)


@pytest.mark.usefixtures("client")
def test_get_game_mode_by_id(client: TestClient):
    igdb_id = 126
    resp_igdb = client.get(f"/igdb/game/{igdb_id}")
    assert resp_igdb.status_code == 200

    resp_all = client.get("/modes/")
    assert resp_all.status_code == 200
    modes = resp_all.json()
    assert len(modes) > 0

    mode_id = modes[0]["id"]
    resp_get = client.get(f"/modes/{mode_id}")
    assert resp_get.status_code == 200
    mode = resp_get.json()
    assert mode["id"] == mode_id
    assert "name" in mode
