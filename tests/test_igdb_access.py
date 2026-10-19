"""
IGDB endpoints: search is admin-only; the (public) update-status check is cached so
page views can't turn into a stream of IGDB requests.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from gamecubby_api.db import get_db
from gamecubby_api.main import app
from gamecubby_api.models import Base
from gamecubby_api.models.game import Game
from gamecubby_api.routers import igdb as igdb_router
from gamecubby_api.utils import game as game_utils


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


# ---------- /igdb/search ----------

def test_igdb_search_requires_authentication(monkeypatch):
    calls = []

    async def fake_search(q):
        calls.append(q)
        return []

    monkeypatch.setattr(igdb_router, "search_igdb_games", fake_search)
    db = _session()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        no_token = client.get("/igdb/search", params={"q": "zelda"})
        bad_token = client.get("/igdb/search", params={"q": "zelda"}, headers={"Authorization": "Bearer nonsense"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert no_token.status_code in (401, 403)
    assert bad_token.status_code == 401
    assert calls == [], "an unauthenticated request must never reach IGDB"


def test_igdb_search_rejects_oversized_queries_for_admins(monkeypatch):
    from gamecubby_api.utils.auth import get_current_admin

    async def fake_search(q):
        return []

    monkeypatch.setattr(igdb_router, "search_igdb_games", fake_search)
    db = _session()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_admin] = lambda: object()
    try:
        client = TestClient(app)
        assert client.get("/igdb/search", params={"q": "zelda"}).status_code == 200
        assert client.get("/igdb/search", params={"q": "x" * 500}).status_code == 422
    finally:
        app.dependency_overrides.clear()


# ---------- /games/{id}/metadata-update-status ----------

@pytest.fixture(autouse=True)
def _clean_status_cache():
    game_utils._status_cache.clear()
    game_utils._status_inflight.clear()
    yield
    game_utils._status_cache.clear()
    game_utils._status_inflight.clear()


def _game(db, **kw):
    g = Game(name="G", igdb_id=kw.pop("igdb_id", 77), updated_at=kw.pop("updated_at", 100), **kw)
    db.add(g)
    db.commit()
    return g


def test_status_check_is_cached_and_shared_between_concurrent_requests(monkeypatch):
    db = _session()
    g = _game(db)
    calls = []

    async def fake_fetch(igdb_id):
        calls.append(igdb_id)
        await asyncio.sleep(0.05)
        return {"updated_at": 200}

    monkeypatch.setattr(game_utils, "fetch_igdb_game", fake_fetch)

    async def run():
        first = await asyncio.gather(*[game_utils.check_game_metadata_status(db, g.id) for _ in range(10)])
        again = await game_utils.check_game_metadata_status(db, g.id)
        return first, again

    first, again = asyncio.run(run())
    assert len(calls) == 1, "10 concurrent page views + a repeat must cost a single IGDB request"
    assert all(r["checked"] and r["update_available"] for r in first) and again["update_available"]


def test_refreshing_a_game_invalidates_its_cached_status(monkeypatch):
    db = _session()
    g = _game(db)
    calls = []

    async def fake_fetch(igdb_id):
        calls.append(igdb_id)
        return {"updated_at": 200}

    monkeypatch.setattr(game_utils, "fetch_igdb_game", fake_fetch)

    async def run():
        before = await game_utils.check_game_metadata_status(db, g.id)
        g.updated_at = 200  # what an admin-triggered metadata refresh does
        db.commit()
        after = await game_utils.check_game_metadata_status(db, g.id)
        return before, after

    before, after = asyncio.run(run())
    assert before["update_available"] is True
    assert after["update_available"] is False and after["checked"] is True
    assert len(calls) == 2


def test_igdb_failures_are_remembered_briefly_not_retried_per_page_view(monkeypatch):
    db = _session()
    g = _game(db)
    calls = []

    async def failing_fetch(igdb_id):
        calls.append(igdb_id)
        raise RuntimeError("IGDB request failed after 4 attempts")

    monkeypatch.setattr(game_utils, "fetch_igdb_game", failing_fetch)

    async def run():
        return [await game_utils.check_game_metadata_status(db, g.id) for _ in range(5)]

    results = asyncio.run(run())
    assert len(calls) == 1
    assert all(r["checked"] is False and r["update_available"] is False for r in results)


def test_status_check_never_modifies_the_game(monkeypatch):
    db = _session()
    g = _game(db)

    async def fake_fetch(igdb_id):
        return {"updated_at": 999}

    monkeypatch.setattr(game_utils, "fetch_igdb_game", fake_fetch)
    asyncio.run(game_utils.check_game_metadata_status(db, g.id))
    db.refresh(g)
    assert g.updated_at == 100  # a public visitor can't trigger/perform an update
