import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    from conftest import get_authenticated_client
    return get_authenticated_client()


def test_create_tag_upsert(client: TestClient):
    resp1 = client.post("/tags/", params={"name": "Strategy"})
    assert resp1.status_code == 200
    tag1 = resp1.json()
    assert tag1["name"] == "strategy"
    assert "id" in tag1

    resp2 = client.post("/tags/", params={"name": "Strategy"})
    assert resp2.status_code == 200
    tag2 = resp2.json()
    assert tag2["name"] == "strategy"
    assert tag2["id"] == tag1["id"]


def test_get_tag_by_id(client: TestClient):
    tag_id = client.post("/tags/", params={"name": "Shooter"}).json()["id"]
    resp_get = client.get(f"/tags/{tag_id}")
    assert resp_get.status_code == 200
    tag = resp_get.json()
    assert tag["id"] == tag_id
    assert tag["name"] == "shooter"


def test_list_tags(client: TestClient):
    tag_id = client.post("/tags/", params={"name": "Adventure"}).json()["id"]
    resp = client.get("/tags/")
    assert resp.status_code == 200
    tags = resp.json()
    assert isinstance(tags, list)
    assert any(t["id"] == tag_id and t["name"] == "adventure" for t in tags)


def test_get_nonexistent_tag_returns_404(client: TestClient):
    resp = client.get("/tags/999999")
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"]["error"] == "not_found"
    assert data["detail"]["detail"] == "Tag not found"


def test_delete_nonexistent_tag_returns_404(client: TestClient):
    resp = client.delete("/tags/999999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Tag not found"
