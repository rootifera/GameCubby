import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    from conftest import get_authenticated_client
    return get_authenticated_client()

def test_list_genres(client: TestClient):
    resp = client.get("/genres/")
    assert resp.status_code == 200
    genres = resp.json()
    assert isinstance(genres, list)


def test_get_genre_by_id(client: TestClient):
    resp_list = client.get("/genres/")
    assert resp_list.status_code == 200
    genres = resp_list.json()
    assert isinstance(genres, list)
    assert len(genres) > 0
    genre = genres[0]
    genre_id = genre["id"]

    resp_get = client.get(f"/genres/{genre_id}")
    assert resp_get.status_code == 200
    genre_fetched = resp_get.json()
    assert genre_fetched["id"] == genre_id
    assert genre_fetched["name"] == genre["name"]
