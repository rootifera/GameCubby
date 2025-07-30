import io
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from conftest import get_authenticated_client
    return get_authenticated_client()


def test_file_shared_between_manual_copies(client: TestClient):
    game_payload = {
        "name": "Age of Empires",
        "summary": "Copy",
        "release_date": 1997,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0,
    }
    game_id1 = client.post("/games/", json=game_payload).json()["id"]
    game_id2 = client.post("/games/", json=game_payload).json()["id"]

    file_content = b"This is a test file."
    files = {"file": ("testfile.txt", io.BytesIO(file_content), "text/plain")}
    data = {"file_type": "files", "label": "Manual"}

    resp_upload = client.post(f"/games/{game_id1}/files/upload", data=data, files=files)
    if resp_upload.status_code == 409:
        error = resp_upload.json()
        assert error["detail"]["error"] == "file_exists"
    else:
        assert resp_upload.status_code == 200
        assert resp_upload.json()["status"] == "success"

    resp_list = client.get(f"/games/{game_id2}/files/")
    assert resp_list.status_code == 200
    file_list = resp_list.json()
    assert any(f["label"] == "Manual" for f in file_list)
    assert any("testfile.txt" in f["path"] for f in file_list)


def test_delete_file(client: TestClient):
    game_id = client.post("/games/", json={
        "name": "Test Delete Game",
        "summary": "For delete file test",
        "release_date": 2024,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0,
    }).json()["id"]

    file_content = b"File to be deleted"
    files = {"file": ("delete_me.txt", io.BytesIO(file_content), "text/plain")}
    data = {"file_type": "files", "label": "ToDelete"}
    file_id = client.post(f"/games/{game_id}/files/upload", data=data, files=files).json()["file_id"]

    resp_delete = client.delete(f"/games/{game_id}/files/{file_id}")
    assert resp_delete.status_code == 204

    resp_list = client.get(f"/games/{game_id}/files/")
    assert all(f["id"] != file_id for f in resp_list.json())


def test_download_file(client: TestClient):
    game_id = client.post("/games/", json={
        "name": "Test Download Game",
        "summary": "For download test",
        "release_date": 2024,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0,
    }).json()["id"]

    file_content = b"Download me!"
    files = {"file": ("download.txt", io.BytesIO(file_content), "text/plain")}
    data = {"file_type": "files", "label": "DownloadTest"}

    resp_upload = client.post(f"/games/{game_id}/files/upload", data=data, files=files)
    if resp_upload.status_code == 409:
        return  # File already existed

    file_id = resp_upload.json()["file_id"]
    resp_download = client.get(f"/downloads/{file_id}")
    assert resp_download.status_code == 200
    assert resp_download.content == file_content
    assert "download.txt" in resp_download.headers.get("content-disposition", "")


def test_sync_files_for_game(client: TestClient):
    game_id = client.post("/games/", json={
        "name": "SyncTestGame",
        "summary": "Testing sync files",
        "release_date": 2024,
        "platforms": [],
        "condition": 1,
        "location_id": None,
        "order": None,
        "collection_id": None,
        "cover_url": None,
        "igdb_id": 0,
    }).json()["id"]

    resp_sync = client.post(f"/games/{game_id}/files/sync-files")
    assert resp_sync.status_code == 200
    data = resp_sync.json()
    assert data["status"] == "success"
    assert data["game_id"] == game_id
    assert "added_files" in data
    assert "skipped_files" in data


def test_full_system_sync(client: TestClient):
    resp = client.post("/files/sync-all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert "sync started" in data["message"].lower()
