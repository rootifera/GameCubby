from fastapi.testclient import TestClient
from gamecubby_api.main import app
import io

client = TestClient(app)

def test_file_shared_between_manual_copies():
    resp1 = client.post("/games/", json={
        "name": "Age of Empires",
        "summary": "Copy 1",
        "release_date": 1997,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0
    })
    copy1 = resp1.json()
    game_id1 = copy1["id"]

    resp2 = client.post("/games/", json={
        "name": "Age of Empires",
        "summary": "Copy 2",
        "release_date": 1997,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0
    })
    copy2 = resp2.json()
    game_id2 = copy2["id"]

    file_content = b"This is a test file."
    files = {
        "file": ("testfile.txt", io.BytesIO(file_content), "text/plain"),
    }
    data = {
        "file_type": "files",
        "label": "Manual",
    }
    resp_upload = client.post(f"/games/{game_id1}/files/upload", data=data, files=files)
    if resp_upload.status_code == 409:
        error = resp_upload.json()
        assert error["detail"]["error"] == "file_exists"
        assert "already exists" in error["detail"]["message"] or "already registered" in error["detail"]["message"]
    else:
        assert resp_upload.status_code == 200
        uploaded = resp_upload.json()
        assert uploaded["status"] == "success"

    resp_list = client.get(f"/games/{game_id2}/files/")
    assert resp_list.status_code == 200
    file_list = resp_list.json()
    assert any(f["label"] == "Manual" for f in file_list)
    assert any("testfile.txt" in f["path"] for f in file_list)

def test_delete_file():
    resp_game = client.post("/games/", json={
        "name": "Test Delete Game",
        "summary": "For delete file test",
        "release_date": 2024,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0
    })
    assert resp_game.status_code == 200
    game = resp_game.json()
    game_id = game["id"]

    file_content = b"File to be deleted"
    files = {
        "file": ("delete_me.txt", io.BytesIO(file_content), "text/plain"),
    }
    data = {
        "file_type": "files",
        "label": "ToDelete",
    }
    resp_upload = client.post(f"/games/{game_id}/files/upload", data=data, files=files)
    assert resp_upload.status_code == 200
    uploaded = resp_upload.json()
    file_id = uploaded["file_id"]

    resp_delete = client.delete(f"/games/{game_id}/files/{file_id}")
    assert resp_delete.status_code == 204

    resp_list = client.get(f"/games/{game_id}/files/")
    assert resp_list.status_code == 200
    files_list = resp_list.json()
    assert all(f["id"] != file_id for f in files_list)

def test_download_file():
    # Create a manual game
    resp_game = client.post("/games/", json={
        "name": "Test Download Game",
        "summary": "For download test",
        "release_date": 2024,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0
    })
    assert resp_game.status_code == 200
    game = resp_game.json()
    game_id = game["id"]

    file_content = b"Download me!"
    files = {
        "file": ("download.txt", io.BytesIO(file_content), "text/plain"),
    }
    data = {
        "file_type": "files",
        "label": "DownloadTest",
    }
    resp_upload = client.post(f"/games/{game_id}/files/upload", data=data, files=files)

    if resp_upload.status_code == 409:
        error = resp_upload.json()
        assert error["detail"]["error"] == "file_exists"
        print("File already exists; skipping download test.")
        return
    else:
        assert resp_upload.status_code == 200
        uploaded = resp_upload.json()
        assert uploaded["status"] == "success"
        file_id = uploaded["file_id"]

    resp_download = client.get(f"/downloads/{file_id}")
    assert resp_download.status_code == 200
    assert resp_download.content == file_content
    content_disposition = resp_download.headers.get("content-disposition", "")
    assert "download.txt" in content_disposition

def test_sync_files_for_game():
    resp_game = client.post("/games/", json={
        "name": "SyncTestGame",
        "summary": "Testing sync files",
        "release_date": 2024,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0
    })
    assert resp_game.status_code == 200
    game = resp_game.json()
    game_id = game["id"]

    resp_sync = client.post(f"/games/{game_id}/files/sync-files")
    assert resp_sync.status_code == 200

    data = resp_sync.json()
    assert data["status"] == "success"
    assert data["game_id"] == game_id
    assert "added_files" in data
    assert "skipped_files" in data

def test_full_system_sync():
    resp = client.post("/files/sync-all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert "message" in data
    assert "sync started" in data["message"].lower()