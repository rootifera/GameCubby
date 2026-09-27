"""Destructive integration tests for a disposable PostgreSQL database.

Run only through scripts/test-api-integration.sh.  The module deliberately
refuses to run unless RUN_POSTGRES_INTEGRATION=1 is set.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

if __import__("os").environ.get("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip("requires the disposable PostgreSQL integration database", allow_module_level=True)

from gamecubby_api.db import SessionLocal, engine
from gamecubby_api.main import app
from gamecubby_api.models import Base
from gamecubby_api.models.admin import AdminUser
from gamecubby_api.models.app_config import AppConfig
from gamecubby_api.models.game import Game
from gamecubby_api.models.platform import Platform
from gamecubby_api.models.genre import Genre
from gamecubby_api.models.mode import Mode
from gamecubby_api.models.playerperspective import PlayerPerspective
from gamecubby_api.models.company import Company
from gamecubby_api.models.collection import Collection
from gamecubby_api.models.igdb_tag import IGDBTag
from gamecubby_api.utils import storage
from gamecubby_api.utils.job_lock import try_job_lock
from gamecubby_api.utils.setup import perform_first_run_setup
from gamecubby_api.routers import company as company_router
from gamecubby_api.routers import collections as collections_router
from gamecubby_api.routers import genres as genres_router
from gamecubby_api.routers import igdb as igdb_router
from gamecubby_api.routers import modes as modes_router
from gamecubby_api.routers import playerperspectives as perspectives_router
from gamecubby_api.routers import games as games_router
from gamecubby_api.routers import storage as storage_router
from gamecubby_api.routers import wishlist as wishlist_router


@pytest.fixture(autouse=True)
def empty_database():
    tables = ", ".join(table.name for table in reversed(Base.metadata.sorted_tables))
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    yield


def _setup(username: str = "integration-admin") -> None:
    db = SessionLocal()
    try:
        perform_first_run_setup(
            db=db,
            admin_username=username,
            admin_password="integration-password",
            igdb_client_id="integration-client",
            igdb_client_secret="integration-secret",
            query_limit=50,
        )
    finally:
        db.close()


def test_setup_is_atomic_and_concurrent():
    def setup_once(username: str):
        db = SessionLocal()
        try:
            _setup(username)
            return "success"
        except ValueError:
            return "already-completed"
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(setup_once, ["admin-one", "admin-two"]))

    assert sorted(results) == ["already-completed", "success"]
    with SessionLocal() as db:
        assert db.query(AdminUser).count() == 1
        assert db.query(AppConfig).filter_by(key="is_firstrun_done", value="true").count() == 1
        assert db.query(AppConfig).count() == 14


def test_postgres_advisory_lock_is_exclusive():
    with try_job_lock("integration-test-lock") as first:
        assert first is True
        with try_job_lock("integration-test-lock") as second:
            assert second is False


def test_file_sync_reports_orphans_without_deleting_them(tmp_path, monkeypatch):
    _setup()
    uploads = tmp_path / "uploads"
    orphan_file = uploads / "local" / "orphan-game" / "other" / "keep-me.txt"
    orphan_file.parent.mkdir(parents=True)
    orphan_file.write_text("retain this", encoding="utf-8")
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(storage, "UPLOADS_DIR", uploads)

    with SessionLocal() as db:
        result = storage.sync_all_files(db)

    assert str(orphan_file.parent.parent) in result["orphan_folders"]
    assert orphan_file.exists()


def test_live_api_uses_database_for_readiness_auth_and_bounded_search():
    _setup()
    with SessionLocal() as db:
        db.add_all([Game(name=f"Integration Game {i:03d}", igdb_id=0) for i in range(205)])
        db.commit()

    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/first_run/status").json() is True
    assert client.get("/admin/maintenance/status").status_code == 200
    assert client.get("/health/ready").status_code == 200
    assert client.post("/company/sync").status_code in {401, 403}

    login = client.post(
        "/auth/login",
        json={"username": "integration-admin", "password": "integration-password"},
    )
    assert login.status_code == 200

    default_results = client.get("/search/basic?name=Integration+Game").json()["results"]
    capped_results = client.get("/search/basic?name=Integration+Game&limit=9999").json()["results"]
    paged_results = client.get("/search/basic?name=Integration+Game&limit=5&offset=200").json()["results"]

    assert len(default_results) == 100
    assert len(capped_results) == 200
    assert len(paged_results) == 5
    assert client.get("/search/basic?name=Integration+Game&limit=0").status_code == 422


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"username": "integration-admin", "password": "integration-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_live_api_exercises_backup_restore_guard_and_maintenance_mode():
    _setup()
    client = TestClient(app)
    headers = _admin_headers(client)

    # Saved backups use the configured local backend during the disposable test.
    saved = client.post("/backup/save", headers=headers)
    assert saved.status_code == 200
    body = saved.json()
    assert body["ok"] is True
    assert body["saved_bytes"] > 0
    saved_path = Path(body["saved_path"])
    assert saved_path.exists()

    streamed = client.get("/backup/", headers=headers)
    assert streamed.status_code == 200
    assert streamed.content.startswith(b"PGDMP")

    assert client.post("/admin/maintenance/enter").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/games/").status_code == 503
    assert client.post("/admin/maintenance/exit").status_code == 200
    assert client.get("/games/").status_code == 200

    saved_path.unlink(missing_ok=True)


def test_live_api_exercises_manual_game_storage_and_wishlist_lifecycle(tmp_path, monkeypatch):
    _setup()
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path / "uploads")
    client = TestClient(app)
    headers = _admin_headers(client)

    tag = client.post("/tags/?name=integration-tag", headers=headers)
    assert tag.status_code == 200
    location = client.post("/locations/?name=Integration+Shelf&type=shelf", headers=headers)
    assert location.status_code == 200
    game = client.post("/games/", headers=headers, json={
        "name": "Integration Manual Game",
        "location_id": location.json()["id"],
        "tag_ids": [tag.json()["id"]],
    })
    assert game.status_code == 200
    game_id = game.json()["id"]

    uploaded = client.post(
        f"/games/{game_id}/files/upload",
        headers=headers,
        data={"label": "Integration save", "category": "saves"},
        files={"file": ("save.sav", b"integration-save", "application/octet-stream")},
    )
    assert uploaded.status_code == 200
    file_id = uploaded.json()["file_id"]
    assert client.get(f"/games/{game_id}/files/").status_code == 200
    assert client.patch(
        f"/games/{game_id}/files/{file_id}/label",
        headers=headers,
        json={"label": "Renamed save"},
    ).status_code == 200
    assert client.delete(f"/games/{game_id}/files/{file_id}", headers=headers).status_code == 204

    wishlist = client.post("/wishlist/", headers=headers, json={"name": "Wanted Game"})
    assert wishlist.status_code == 200
    wishlist_id = wishlist.json()["id"]
    resolved = client.post(
        f"/wishlist/{wishlist_id}/resolve", headers=headers, json={"game_id": game_id}
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "in_library"
    assert client.get("/wishlist/").json() == []
    assert client.get("/wishlist/?status=in_library").json()[0]["id"] == wishlist_id


def test_live_api_exercises_catalog_lookup_search_stats_export_and_configuration():
    _setup()
    with SessionLocal() as db:
        db.add_all([
            Platform(id=6, name="PC"), Genre(id=1, name="Adventure"), Mode(id=1, name="Single player"),
            PlayerPerspective(id=1, name="First person"), Company(id=1, name="Integration Co"),
            Collection(id=1, name="Integration Collection"), IGDBTag(id=1, name="Action"),
        ])
        db.commit()
    client = TestClient(app)
    headers = _admin_headers(client)

    # Configuration CRUD and all public lookup list/detail paths.
    assert client.post("/app_config/", headers=headers, json={"key": "integration_key", "value": "yes"}).status_code == 200
    assert client.get("/app_config/integration_key", headers=headers).status_code == 200
    assert client.get("/app_config/", headers=headers).status_code == 200
    assert client.delete("/app_config/integration_key", headers=headers).status_code == 200
    for path in ("/platforms/", "/platforms/6", "/genres/", "/genres/1", "/modes/", "/modes/1",
                 "/perspectives/", "/perspectives/1", "/company/", "/company/1", "/collections/", "/collections/1",
                 "/igdb/tags/1"):
        assert client.get(path).status_code == 200, path

    tag = client.post("/tags/?name=searchable", headers=headers).json()
    location = client.post("/locations/?name=Root&type=root", headers=headers).json()
    child = client.post(f"/locations/?name=Child&parent_id={location['id']}&type=shelf", headers=headers).json()
    game = client.post("/games/", headers=headers, json={
        "name": "Searchable Integration Game", "release_date": 2000, "platform_ids": [6],
        "genre_ids": [1], "mode_ids": [1], "player_perspective_ids": [1], "company_ids": [1],
        "collection_id": 1, "tag_ids": [tag["id"]], "location_id": child["id"],
    }).json()
    game_id = game["id"]

    # Location, tag, game, basic/advanced search, suggestion, stats, and export operations.
    for path in (f"/locations/{location['id']}", "/locations/", "/locations/top", f"/locations/children/{location['id']}",
                 f"/locations/{child['id']}/games", "/tags/", f"/tags/{tag['id']}", "/games/", f"/games/{game_id}",
                 f"/games/{game_id}/location_path", "/search/basic?name=Searchable", "/search/advanced?name=Searchable",
                 "/search/suggest/names?q=Se", "/search/suggest/tags?q=se", "/search/suggest/igdb_tags?q=Ac",
                 "/search/suggest/modes?q=Si", "/search/suggest/collections?q=In", "/search/suggest/companies?q=In",
                 "/stats/overview", "/stats/health", "/stats/health/cover", "/stats/health/release_year",
                 "/stats/health/platform", "/stats/health/location", "/stats/health/tag"):
        assert client.get(path).status_code == 200, path
    for path in ("/export/games/json", "/export/games/csv", "/export/games/excel"):
        assert client.get(path, headers=headers).status_code == 200, path

    assert client.put(f"/games/{game_id}", headers=headers, json={"condition": 4}).status_code == 200
    assert client.put(f"/locations/{child['id']}/rename", headers=headers, json={"name": "Renamed Child"}).status_code == 200
    assert client.post("/locations/migrate", headers=headers, json={"source_location_id": child["id"], "target_location_id": location["id"]}).status_code == 200
    assert client.post("/stats/force_refresh", headers=headers).status_code == 200
    assert client.delete(f"/tags/{tag['id']}", headers=headers).status_code == 200
    assert client.delete(f"/games/{game_id}", headers=headers).status_code == 200
    assert client.delete(f"/locations/{child['id']}", headers=headers).status_code == 204


def test_live_api_exercises_igdb_and_lookup_sync_routes_with_provider_mocks(monkeypatch):
    _setup()
    client = TestClient(app)
    headers = _admin_headers(client)

    raw_game = {"id": 99, "name": "Mock IGDB Game", "summary": "mock", "first_release_date": 946684800,
                "platforms": [{"id": 6, "name": "PC"}], "tags": [], "involved_companies": []}

    async def search_igdb(_query): return [raw_game]
    async def fetch_game(_game_id): return raw_game
    async def fetch_collection(_game_id): return []
    async def empty_tags(*_args, **_kwargs): return []
    async def sync_genres(_db): return [{"id": 1, "name": "Adventure"}]
    async def sync_perspectives(_db): return 1
    async def sync_modes(_db): return 1
    async def sync_companies(): return 1

    monkeypatch.setattr(igdb_router, "search_igdb_games", search_igdb)
    monkeypatch.setattr(igdb_router, "fetch_igdb_game", fetch_game)
    monkeypatch.setattr(igdb_router, "fetch_igdb_collection", fetch_collection)
    monkeypatch.setattr(collections_router, "fetch_igdb_collection", fetch_collection)
    monkeypatch.setattr(igdb_router, "upsert_igdb_tags", empty_tags)
    monkeypatch.setattr(genres_router, "sync_genres", sync_genres)
    monkeypatch.setattr(perspectives_router, "sync_player_perspectives", sync_perspectives)
    monkeypatch.setattr(modes_router, "sync_modes", sync_modes)
    monkeypatch.setattr(company_router, "sync_companies", sync_companies)

    assert client.get("/igdb/search?q=Mock").status_code == 200
    assert client.get("/igdb/search?q=x").status_code == 400
    assert client.get("/igdb/game/99", headers=headers).status_code == 200
    assert client.get("/igdb/game/999", headers=headers).status_code == 200
    assert client.post("/genres/sync", headers=headers).status_code == 200
    assert client.post("/perspectives/sync", headers=headers).status_code == 200
    assert client.post("/modes/sync", headers=headers).status_code == 200
    assert client.post("/company/sync", headers=headers).status_code == 200
    assert client.get("/collections/collection_lookup/99", headers=headers).status_code == 200
    assert client.get("/backup/list", headers=headers).status_code == 200
    assert client.post("/backup/sync-storage", headers=headers, json={"source": "local", "target": "local"}).status_code == 400


def test_live_api_exercises_wishlist_mutations_purchase_and_igdb_create(monkeypatch):
    _setup()
    client = TestClient(app)
    headers = _admin_headers(client)
    with SessionLocal() as db:
        db.add(Platform(id=6, name="PC"))
        db.commit()

    # The manual workflow supports edit, public read, purchase, and delete.
    created = client.post("/wishlist/", headers=headers, json={
        "name": "Manual wanted game", "release_year": 1999, "platform_ids": [6],
        "links": [{"label": "eBay", "url": "https://example.test/listing"}],
    })
    assert created.status_code == 200
    wishlist_id = created.json()["id"]
    assert client.get(f"/wishlist/{wishlist_id}").status_code == 200
    updated = client.put(f"/wishlist/{wishlist_id}", headers=headers, json={"name": "Edited wanted game", "links": []})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Edited wanted game"
    purchased = client.post(f"/wishlist/{wishlist_id}/purchase", headers=headers, json={"condition": 3})
    assert purchased.status_code == 200
    assert purchased.json()["igdb_id"] == 0
    assert client.post(f"/wishlist/{wishlist_id}/purchase", headers=headers, json={}).status_code == 409

    removable = client.post("/wishlist/", headers=headers, json={"name": "Remove me"}).json()["id"]
    assert client.delete(f"/wishlist/{removable}", headers=headers).status_code == 204
    assert client.get(f"/wishlist/{removable}").status_code == 404
    assert client.post("/wishlist/", json={"name": "unauthorised"}).status_code in {401, 403}
    assert client.get("/wishlist/?status=not-a-status").status_code == 422

    raw_game = {"id": 777, "name": "IGDB wanted game", "summary": "mock", "first_release_date": 946684800,
                "platforms": [{"id": 6, "name": "PC"}], "tags": [], "involved_companies": []}

    async def fetch_game(_game_id): return raw_game
    async def fetch_collection(_game_id): return []
    async def no_tags(*_args, **_kwargs): return []

    monkeypatch.setattr(wishlist_router, "fetch_igdb_game", fetch_game)
    monkeypatch.setattr(games_router, "add_game_from_igdb", __import__("gamecubby_api.utils.game", fromlist=["add_game_from_igdb"]).add_game_from_igdb)
    # The IGDB creation utility imports these provider calls in its own module.
    game_utils = __import__("gamecubby_api.utils.game", fromlist=["fetch_igdb_game"])
    monkeypatch.setattr(game_utils, "fetch_igdb_game", fetch_game)
    monkeypatch.setattr(game_utils, "fetch_igdb_collection", fetch_collection)
    monkeypatch.setattr(game_utils, "upsert_igdb_tags", no_tags)

    from_igdb = client.post("/wishlist/from_igdb", headers=headers, json={"igdb_id": 777, "platform_ids": [6]})
    assert from_igdb.status_code == 200
    resolved = client.post("/games/from_igdb", headers=headers, json={
        "igdb_id": 777, "platform_ids": [6], "wishlist_id": from_igdb.json()["id"],
    })
    assert resolved.status_code == 200
    assert client.get("/wishlist/?include_resolved=true").json()[-1]["status"] == "in_library"


def test_live_api_exercises_file_system_and_metadata_jobs(tmp_path, monkeypatch):
    _setup()
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(storage_router, "SYNC_STATUS_FILE", tmp_path / "sync-status.json")
    monkeypatch.setattr(games_router, "METADATA_REFRESH_STATUS_FILE", tmp_path / "metadata-status.json")
    client = TestClient(app)
    headers = _admin_headers(client)
    game = client.post("/games/", headers=headers, json={"name": "Job game"}).json()
    game_id = game["id"]

    assert client.get(f"/games/{game_id}/files/?category=saves").status_code == 200
    assert client.post(f"/games/{game_id}/files/sync-files", headers=headers).status_code == 200
    assert client.get("/files/categories").status_code == 200
    assert client.get("/files/sync-all/status", headers=headers).json()["status"] == "idle"

    def fake_sync_all(_db): return {"added": 0, "skipped": 0, "orphan_folders": []}
    def fake_sync_backends(_db, source, target): return {"source": source, "target": target, "copied": 0}
    monkeypatch.setattr(storage_router, "sync_all_files", fake_sync_all)
    monkeypatch.setattr(storage_router, "sync_storage_backends", fake_sync_backends)
    assert client.post("/files/sync-all", headers=headers).status_code == 200
    assert client.get("/files/sync-all/status", headers=headers).json()["status"] == "completed"
    assert client.post("/files/sync-storage", headers=headers, json={"source": "local", "target": "local"}).status_code == 200
    assert client.get("/downloads/999999").status_code == 403
    assert client.get("/downloads/999999", headers=headers).status_code == 404

    # Metadata routes include custom conversion, one-game refresh and both job types.
    with SessionLocal() as db:
        db_game = db.get(Game, game_id)
        db_game.igdb_id = 123
        db_game.updated_at = 1
        db.commit()

    async def fake_refresh(db, identifier):
        return db.get(Game, identifier), True, "updated"
    def fake_all(_db): return {"updated": 1, "skipped": 0, "errors": 0}
    def fake_force(_db): return {"updated": 1, "skipped": 0, "errors": 0}
    monkeypatch.setattr(games_router, "refresh_game_metadata", fake_refresh)
    monkeypatch.setattr(games_router, "refresh_all_games_metadata", fake_all)
    monkeypatch.setattr(games_router, "force_refresh_metadata", fake_force)
    assert client.post(f"/games/{game_id}/refresh_metadata", headers=headers).status_code == 200
    assert client.post("/games/refresh_all_metadata", headers=headers).status_code == 200
    assert client.get("/games/refresh_all_metadata/status", headers=headers).json()["status"] == "completed"
    assert client.post("/games/force_refresh_metadata", headers=headers).status_code == 200
    assert client.post(f"/games/{game_id}/convert_to_custom", headers=headers).json()["igdb_id"] == 0
    assert client.post("/auth/change-password", headers=headers, json={"current_password": "wrong", "new_password": "new-password"}).status_code == 401
    assert client.post("/auth/change-password", headers=headers, json={"current_password": "integration-password", "new_password": "new-password"}).status_code == 200
    assert client.post("/auth/login", json={"username": "integration-admin", "password": "new-password"}).status_code == 200


def test_live_api_exercises_purchase_link_shortcut_management():
    _setup()
    client = TestClient(app)
    headers = _admin_headers(client)
    base = "/purchase-link-shortcuts/"

    # Every management operation is admin-only.
    assert client.get(base).status_code in {401, 403}
    assert client.post(base, json={"label": "eBay"}).status_code in {401, 403}
    assert client.put(f"{base}reorder", json={"items": [{"id": 1, "sort_order": 1}]}).status_code in {401, 403}
    assert client.put(f"{base}1", json={"sort_order": 1}).status_code in {401, 403}
    assert client.delete(f"{base}1").status_code in {401, 403}

    assert client.post(base, headers=headers, json={"label": "   "}).status_code == 422
    assert client.post(base, headers=headers, json={"label": "x" * 101}).status_code == 422
    ebay = client.post(base, headers=headers, json={"label": " eBay ", "sort_order": 10})
    assert ebay.status_code == 201
    assert ebay.json()["label"] == "eBay"
    assert client.post(base, headers=headers, json={"label": " EBAY "}).status_code == 409
    cex = client.post(base, headers=headers, json={"label": "CeX", "sort_order": 20}).json()
    local = client.post(base, headers=headers, json={"label": "Local shop", "sort_order": 5}).json()
    assert [item["label"] for item in client.get(base, headers=headers).json()] == ["Local shop", "eBay", "CeX"]

    updated = client.put(f"{base}{ebay.json()['id']}", headers=headers, json={"label": "eBay UK", "sort_order": 30})
    assert updated.status_code == 200
    assert updated.json()["label"] == "eBay UK"
    reordered = client.put(base + "reorder", headers=headers, json={"items": [
        {"id": cex["id"], "sort_order": 1}, {"id": local["id"], "sort_order": 2},
    ]})
    assert reordered.status_code == 200
    assert [item["id"] for item in reordered.json()][:2] == [cex["id"], local["id"]]
    assert client.put(base + "reorder", headers=headers, json={"items": [{"id": 999, "sort_order": 1}]}).status_code == 404

    wishlist = client.post("/wishlist/", headers=headers, json={
        "name": "Linked Wishlist Game", "links": [{"label": "eBay UK", "url": "https://example.test/ebay"}],
    })
    assert wishlist.status_code == 200
    assert client.delete(f"{base}{ebay.json()['id']}", headers=headers).status_code == 204
    assert client.get(f"/wishlist/{wishlist.json()['id']}").json()["links"][0]["label"] == "eBay UK"
