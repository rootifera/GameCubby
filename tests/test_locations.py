import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    from conftest import get_authenticated_client
    return get_authenticated_client()


def test_create_location(client: TestClient):
    resp = client.post("/locations/", params={"name": "Bookcase A"})
    assert resp.status_code == 200
    location = resp.json()
    assert location["name"] == "Bookcase A"
    assert location["parent_id"] is None
    assert "id" in location


def test_create_child_location(client: TestClient):
    resp_parent = client.post("/locations/", params={"name": "Shelf B"})
    assert resp_parent.status_code == 200
    parent = resp_parent.json()
    parent_id = parent["id"]

    resp_child = client.post("/locations/", params={"name": "Box 1", "parent_id": parent_id})
    assert resp_child.status_code == 200
    child = resp_child.json()
    assert child["name"] == "Box 1"
    assert child["parent_id"] == parent_id
    assert "id" in child


def test_list_top_locations(client: TestClient):
    resp = client.post("/locations/", params={"name": "Top Shelf"})
    assert resp.status_code == 200
    location = resp.json()
    loc_id = location["id"]

    resp_list = client.get("/locations/top")
    assert resp_list.status_code == 200
    locations = resp_list.json()
    assert isinstance(locations, list)
    assert any(l["id"] == loc_id and l["parent_id"] is None for l in locations)


def test_list_child_locations(client: TestClient):
    resp_parent = client.post("/locations/", params={"name": "Shelf C"})
    assert resp_parent.status_code == 200
    parent = resp_parent.json()
    parent_id = parent["id"]

    resp_child1 = client.post("/locations/", params={"name": "Box 2", "parent_id": parent_id})
    assert resp_child1.status_code == 200
    resp_child2 = client.post("/locations/", params={"name": "Box 3", "parent_id": parent_id})
    assert resp_child2.status_code == 200

    resp_children = client.get(f"/locations/children/{parent_id}")
    assert resp_children.status_code == 200
    children = resp_children.json()
    assert isinstance(children, list)
    names = [c["name"] for c in children]
    assert "Box 2" in names
    assert "Box 3" in names


def test_list_all_locations(client: TestClient):
    resp1 = client.post("/locations/", params={"name": "Cupboard"})
    assert resp1.status_code == 200
    resp2 = client.post("/locations/", params={"name": "Drawer"})
    assert resp2.status_code == 200

    resp = client.get("/locations/")
    assert resp.status_code == 200
    ids = [l["id"] for l in resp.json()]
    assert resp1.json()["id"] in ids
    assert resp2.json()["id"] in ids


def test_get_location_by_id(client: TestClient):
    resp_create = client.post("/locations/", params={"name": "Bin"})
    assert resp_create.status_code == 200
    loc_id = resp_create.json()["id"]

    resp_get = client.get(f"/locations/{loc_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == loc_id
    assert resp_get.json()["name"] == "Bin"


def test_get_nonexistent_location_returns_404(client: TestClient):
    resp = client.get("/locations/999999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Location not found"
