import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    from conftest import get_authenticated_client
    return get_authenticated_client()

def test_list_collections(client: TestClient):
    resp = client.get("/collections/")
    assert resp.status_code == 200
    collections = resp.json()
    assert isinstance(collections, list)

def test_get_collection_by_id(client: TestClient):
    # Trigger IGDB lookup to create at least one collection
    client.get("/igdb/game/126")

    resp = client.get("/collections/")
    assert resp.status_code == 200
    collections = resp.json()
    assert len(collections) > 0

    collection = collections[0]
    collection_id = collection["id"]

    resp_get = client.get(f"/collections/{collection_id}")
    assert resp_get.status_code == 200
    got = resp_get.json()
    assert got["id"] == collection_id
    assert got["name"] == collection["name"]

def test_get_nonexistent_collection_returns_404(client: TestClient):
    non_existent_id = 999999
    resp = client.get(f"/collections/{non_existent_id}")
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"] == "Collection not found"
