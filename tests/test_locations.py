from fastapi.testclient import TestClient
from gamecubby_api.main import app

client = TestClient(app)


def test_create_location():
    resp = client.post("/locations/", params={"name": "Bookcase A"})
    assert resp.status_code == 200
    location = resp.json()
    assert location["name"] == "Bookcase A"
    assert location["parent_id"] is None
    assert "id" in location


def test_create_child_location():
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


def test_list_top_locations():
    resp = client.post("/locations/", params={"name": "Top Shelf"})
    assert resp.status_code == 200
    location = resp.json()
    loc_id = location["id"]

    resp_list = client.get("/locations/top")
    assert resp_list.status_code == 200
    locations = resp_list.json()
    assert isinstance(locations, list)
    assert any(l["id"] == loc_id and l["parent_id"] is None for l in locations)


def test_list_child_locations():
    resp_parent = client.post("/locations/", params={"name": "Shelf C"})
    assert resp_parent.status_code == 200
    parent = resp_parent.json()
    parent_id = parent["id"]

    resp_child1 = client.post("/locations/", params={"name": "Box 2", "parent_id": parent_id})
    assert resp_child1.status_code == 200
    child1 = resp_child1.json()
    resp_child2 = client.post("/locations/", params={"name": "Box 3", "parent_id": parent_id})
    assert resp_child2.status_code == 200
    child2 = resp_child2.json()

    resp_children = client.get(f"/locations/children/{parent_id}")
    assert resp_children.status_code == 200
    children = resp_children.json()
    assert isinstance(children, list)
    child_names = [c["name"] for c in children]
    assert "Box 2" in child_names
    assert "Box 3" in child_names


def test_list_all_locations():
    resp1 = client.post("/locations/", params={"name": "Cupboard"})
    assert resp1.status_code == 200
    loc1 = resp1.json()
    resp2 = client.post("/locations/", params={"name": "Drawer"})
    assert resp2.status_code == 200
    loc2 = resp2.json()

    resp = client.get("/locations/")
    assert resp.status_code == 200
    locations = resp.json()
    ids = [l["id"] for l in locations]
    assert loc1["id"] in ids
    assert loc2["id"] in ids


def test_get_location_by_id():
    resp_create = client.post("/locations/", params={"name": "Bin"})
    assert resp_create.status_code == 200
    location = resp_create.json()
    location_id = location["id"]

    resp_get = client.get(f"/locations/{location_id}")
    assert resp_get.status_code == 200
    loc_got = resp_get.json()
    assert loc_got["id"] == location_id
    assert loc_got["name"] == "Bin"


def test_get_nonexistent_location_returns_404():
    non_existent_id = 999999
    resp = client.get(f"/locations/{non_existent_id}")
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"] == "Location not found"
