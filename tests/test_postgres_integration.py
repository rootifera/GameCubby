"""Destructive integration tests for a disposable PostgreSQL database.

Run only through scripts/test-api-integration.sh.  The module deliberately
refuses to run unless RUN_POSTGRES_INTEGRATION=1 is set.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

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
from gamecubby_api.utils import storage
from gamecubby_api.utils.job_lock import try_job_lock
from gamecubby_api.utils.setup import perform_first_run_setup


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

