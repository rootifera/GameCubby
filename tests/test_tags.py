from fastapi.testclient import TestClient
from gamecubby_api.main import app

client = TestClient(app)


def test_create_tag_upsert():
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


def test_get_tag_by_id():
    resp_create = client.post("/tags/", params={"name": "Shooter"})
    assert resp_create.status_code == 200
    tag = resp_create.json()
    tag_id = tag["id"]

    resp_get = client.get(f"/tags/{tag_id}")
    assert resp_get.status_code == 200
    tag_got = resp_get.json()
    assert tag_got["id"] == tag_id
    assert tag_got["name"] == "shooter"


def test_list_tags():
    resp_create = client.post("/tags/", params={"name": "Adventure"})
    assert resp_create.status_code == 200
    tag = resp_create.json()
    tag_id = tag["id"]

    resp_list = client.get("/tags/")
    assert resp_list.status_code == 200
    tags = resp_list.json()
    assert isinstance(tags, list)
    assert any(t["id"] == tag_id and t["name"] == "adventure" for t in tags)


def test_get_nonexistent_tag_returns_404():
    non_existent_id = 999999
    resp = client.get(f"/tags/{non_existent_id}")
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data
    assert data["detail"]["error"] == "not_found"
    assert data["detail"]["detail"] == "Tag not found"


def test_delete_nonexistent_tag_returns_404():
    non_existent_id = 999999
    resp = client.delete(f"/tags/{non_existent_id}")
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"] == "Tag not found"
