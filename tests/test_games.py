from fastapi.testclient import TestClient
from gamecubby_api.main import app

client = TestClient(app)


def test_add_manual_game():
    resp_platforms = client.get("/platforms/")
    assert resp_platforms.status_code == 200
    platforms = resp_platforms.json()
    assert platforms, "No platforms available for testing"
    platform_id = platforms[0]["id"]

    resp_genres = client.get("/genres/")
    assert resp_genres.status_code == 200
    genres = resp_genres.json()
    assert genres, "No genres available for testing"
    genre_id = genres[0]["id"]

    resp = client.post("/games/", json={
        "name": "Test Manual Game",
        "summary": "This is a test manual game",
        "release_date": 2023,
        "platform_ids": [platform_id],
        "genre_ids": [genre_id],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    assert resp.status_code == 200
    game = resp.json()
    assert game["name"] == "Test Manual Game"
    assert "id" in game
    assert any(p["id"] == platform_id for p in game["platforms"])
    assert any(g["id"] == genre_id for g in game["genres"])




def test_get_game_by_id():
    resp_genres = client.get("/genres/")
    genre_id = resp_genres.json()[0]["id"]

    resp_create = client.post("/games/", json={
        "name": "Test Get Game",
        "summary": "Game to retrieve",
        "release_date": 2023,
        "platform_ids": [],
        "genre_ids": [genre_id],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    assert resp_create.status_code == 200
    game = resp_create.json()
    game_id = game["id"]

    resp_get = client.get(f"/games/{game_id}")
    assert resp_get.status_code == 200
    retrieved = resp_get.json()
    assert retrieved["id"] == game_id
    assert retrieved["name"] == "Test Get Game"
    assert any(g["id"] == genre_id for g in retrieved["genres"])



def test_get_game_not_found():
    resp = client.get("/games/999999")
    assert resp.status_code == 404
    error = resp.json()
    assert "detail" in error
    assert error["detail"]["error"] == "not_found"


def test_update_game():
    resp_platforms = client.get("/platforms/")
    assert resp_platforms.status_code == 200
    platforms = resp_platforms.json()
    assert platforms, "No platforms available for testing"
    platform_id = platforms[0]["id"]

    resp_genres = client.get("/genres/")
    assert resp_genres.status_code == 200
    genres = resp_genres.json()
    assert len(genres) >= 2
    genre_ids = [genres[0]["id"], genres[1]["id"]]

    resp_create = client.post("/games/", json={
        "name": "Game To Update",
        "summary": "Original summary",
        "release_date": 2023,
        "platform_ids": [],
        "genre_ids": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    assert resp_create.status_code == 200
    game = resp_create.json()
    game_id = game["id"]

    update_data = {
        "name": "Game Updated",
        "summary": "Updated summary",
        "release_date": 2024,
        "condition": 2,
        "location_id": None,
        "order": 1,
        "collection_id": None,
        "cover_url": None,
        "platform_ids": [platform_id],
        "genre_ids": genre_ids
    }
    resp_update = client.put(f"/games/{game_id}", json=update_data)
    assert resp_update.status_code == 200
    updated = resp_update.json()
    assert updated["name"] == "Game Updated"
    assert updated["summary"] == "Updated summary"
    assert updated["release_date"] == 2024
    assert any(p["id"] == platform_id for p in updated["platforms"])
    assert all(gid in [g["id"] for g in updated["genres"]] for gid in genre_ids)




def test_update_nonexistent_game():
    update_data = {
        "name": "Nonexistent Game",
        "summary": "No game here",
        "release_date": 2024,
        "condition": 1,
        "location_id": None,
        "order": 0,
        "collection_id": None,
        "cover_url": None
    }
    resp_update = client.put("/games/999999", json=update_data)
    assert resp_update.status_code == 404
    error = resp_update.json()
    assert "detail" in error
    assert error["detail"]["error"] == "not_found"


def test_delete_game():
    resp_create = client.post("/games/", json={
        "name": "Game To Delete",
        "summary": "Delete me",
        "release_date": 2023,
        "platform_ids": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    assert resp_create.status_code == 200
    game = resp_create.json()
    game_id = game["id"]

    resp_delete = client.delete(f"/games/{game_id}")
    assert resp_delete.status_code == 200 or resp_delete.status_code == 204 or resp_delete.status_code == 200
    assert resp_delete.json() is True

    resp_get = client.get(f"/games/{game_id}")
    assert resp_get.status_code == 404


def test_delete_nonexistent_game():
    resp_delete = client.delete("/games/999999")
    assert resp_delete.status_code == 404
    error = resp_delete.json()
    assert "detail" in error
    assert error["detail"]["error"] == "not_found"


def test_add_tag_to_game():
    resp_game = client.post("/games/", json={
        "name": "Game with Tag",
        "summary": "Testing tags",
        "release_date": 2023,
        "platform_ids": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    game = resp_game.json()
    game_id = game["id"]

    resp_tag = client.post("/tags/", params={"name": "Action"})
    tag = resp_tag.json()
    tag_id = tag["id"]

    resp_attach = client.post(f"/games/{game_id}/tags/{tag_id}")
    assert resp_attach.status_code == 200
    assert resp_attach.json() is True


def test_remove_tag_from_game():
    resp_game = client.post("/games/", json={
        "name": "Game with Removable Tag",
        "summary": "Testing tag removal",
        "release_date": 2023,
        "platform_ids": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    game = resp_game.json()
    game_id = game["id"]

    resp_tag = client.post("/tags/", params={"name": "Strategy"})
    tag = resp_tag.json()
    tag_id = tag["id"]

    client.post(f"/games/{game_id}/tags/{tag_id}")

    resp_remove = client.delete(f"/games/{game_id}/tags/{tag_id}")
    assert resp_remove.status_code == 200
    assert resp_remove.json() is True


def test_get_tags_for_game():
    resp_game = client.post("/games/", json={
        "name": "Game For Tag List",
        "summary": "Testing tag listing",
        "release_date": 2023,
        "platform_ids": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    game = resp_game.json()
    game_id = game["id"]

    tag_names = ["RPG", "Adventure"]
    tag_ids = []
    for name in tag_names:
        resp_tag = client.post("/tags/", params={"name": name})
        tag = resp_tag.json()
        tag_ids.append(tag["id"])
        client.post(f"/games/{game_id}/tags/{tag['id']}")

    resp = client.get(f"/games/{game_id}/tags")
    assert resp.status_code == 200
    tags = resp.json()
    tag_names_returned = [t["name"] for t in tags]
    for name in tag_names:
        assert name.lower() in tag_names_returned


def test_add_platform_to_game():
    resp_game = client.post("/games/", json={
        "name": "Game with Platform",
        "summary": "Testing platforms",
        "release_date": 2023,
        "platform_ids": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    game = resp_game.json()
    game_id = game["id"]

    resp_platforms = client.get("/platforms/")
    assert resp_platforms.status_code == 200
    platforms = resp_platforms.json()
    assert len(platforms) > 0
    platform_id = platforms[0]["id"]

    resp_attach = client.post(f"/games/{game_id}/platforms/{platform_id}")
    assert resp_attach.status_code == 200
    assert resp_attach.json() is True


def test_remove_platform_from_game():
    resp_game = client.post("/games/", json={
        "name": "Game with Removable Platform",
        "summary": "Testing platform removal",
        "release_date": 2023,
        "platform_ids": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    game = resp_game.json()
    game_id = game["id"]

    resp_platforms = client.get("/platforms/")
    platform_id = resp_platforms.json()[0]["id"]

    client.post(f"/games/{game_id}/platforms/{platform_id}")

    resp_remove = client.delete(f"/games/{game_id}/platforms/{platform_id}")
    assert resp_remove.status_code == 200
    assert resp_remove.json() is True


def test_get_platforms_for_game():
    resp_game = client.post("/games/", json={
        "name": "Game for Platform List",
        "summary": "Testing platform listing",
        "release_date": 2023,
        "platform_ids": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    game = resp_game.json()
    game_id = game["id"]

    resp_platforms = client.get("/platforms/")
    platform_id = resp_platforms.json()[0]["id"]
    client.post(f"/games/{game_id}/platforms/{platform_id}")

    resp = client.get(f"/games/{game_id}/platforms")
    assert resp.status_code == 200
    platforms = resp.json()
    assert any(p["id"] == platform_id for p in platforms)


def test_assign_location_to_game():
    resp_loc = client.post("/locations/", params={"name": "Test Location"})
    assert resp_loc.status_code == 200
    location = resp_loc.json()
    location_id = location["id"]

    resp_game = client.post("/games/", json={
        "name": "Game to Assign Location",
        "summary": "Assign location test",
        "release_date": 2023,
        "platform_ids": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    assert resp_game.status_code == 200
    game = resp_game.json()
    game_id = game["id"]

    data = {"location_id": location_id, "order": 1}
    resp_assign = client.post(f"/games/{game_id}/assign_location", json=data)
    assert resp_assign.status_code == 200
    updated_game = resp_assign.json()

    assert updated_game.get("order") == 1


def test_add_game_from_igdb():
    igdb_id = 262186

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
    assert game["igdb_id"] == igdb_id
    assert "id" in game


def test_get_game_location_path():
    resp_loc = client.post("/locations/", params={"name": "Top Location"})
    location = resp_loc.json()
    location_id = location["id"]

    resp_child_loc = client.post("/locations/", params={"name": "Child Location", "parent_id": location_id})
    child_location = resp_child_loc.json()
    child_location_id = child_location["id"]

    resp_game = client.post("/games/", json={
        "name": "Game With Location Path",
        "summary": "Test location path",
        "release_date": 2023,
        "platform_ids": [],
        "condition": 1,
        "location_id": child_location_id,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "tag_ids": []
    })
    game = resp_game.json()
    game_id = game["id"]

    resp_path = client.get(f"/games/game/{game_id}/location_path")
    assert resp_path.status_code == 200
    path = resp_path.json().get("location_path", [])
    assert isinstance(path, list)
    assert len(path) >= 1
    assert any(loc["id"] == location_id for loc in path)
    assert any(loc["id"] == child_location_id for loc in path)
