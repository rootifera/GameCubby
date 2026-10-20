"""
A flood of requests (e.g. a security scanner) must degrade the API gracefully instead of
freezing it. Root causes fixed: blocking DB calls inside `async def` handlers, thread-pool
starvation against a smaller connection pool, 30 s pool waits, ~11 queries per cover.
"""
import asyncio
import inspect
import sys
import types

import anyio.to_thread
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, TimeoutError as PoolTimeoutError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from gamecubby_api import main as api_main
from gamecubby_api.db import get_db
from gamecubby_api.main import app
from gamecubby_api.models import Base
from gamecubby_api.models.app_config import AppConfig
from gamecubby_api.routers import games as games_router
from gamecubby_api.utils import app_config, storage


# ------------------------------------------------ nothing blocking on the event loop

def test_the_cover_endpoint_runs_in_the_thread_pool_not_on_the_event_loop():
    assert not inspect.iscoroutinefunction(games_router.get_cover)
    assert not inspect.iscoroutinefunction(storage.serve_game_cover)


def test_every_public_async_endpoint_is_free_of_database_sessions():
    """
    A public `async def` endpoint must not take a request-scoped DB session: its blocking
    queries would run on the event loop (and hold a connection across awaits). Public endpoints
    that need to await (IGDB) must fetch their data in a thread, in a short-lived session.
    """
    from gamecubby_api.utils.auth import get_current_admin

    def deps(route):
        out = set()

        def walk(d):
            for sub in d.dependencies:
                if sub.call:
                    out.add(sub.call)
                walk(sub)
        walk(route.dependant)
        return out

    offenders = [
        f"{','.join(sorted(r.methods - {'HEAD', 'OPTIONS'}))} {r.path}"
        for r in app.routes
        if isinstance(r, APIRoute) and inspect.iscoroutinefunction(r.endpoint)
        and get_current_admin not in deps(r) and get_db in deps(r)
    ]
    assert offenders == []


# ------------------------------------------------------ thread pool vs connection pool

def test_thread_pool_is_capped_below_the_connection_pool(monkeypatch):
    monkeypatch.delenv("THREADPOOL_SIZE", raising=False)

    async def run():
        tokens = api_main.configure_threadpool()
        return tokens, anyio.to_thread.current_default_thread_limiter().total_tokens

    tokens, limiter = asyncio.run(run())
    assert tokens == limiter == max(8, api_main.POOL_CAPACITY - 4)
    assert tokens < api_main.POOL_CAPACITY, "a thread must never have to wait for a connection"

    monkeypatch.setenv("THREADPOOL_SIZE", "6")
    assert asyncio.run(run())[0] == 6


# ------------------------------------------------------------- graceful failure (503)

def _client_with_failing_route(exc):
    async def boom():
        raise exc

    app.add_api_route("/__test_boom", boom, methods=["GET"])
    return TestClient(app, raise_server_exceptions=False)


def _drop_test_route():
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/__test_boom"]


def test_pool_exhaustion_returns_503_with_retry_after_not_a_500():
    client = _client_with_failing_route(PoolTimeoutError("QueuePool limit of size 10 overflow 10 reached"))
    try:
        r = client.get("/__test_boom")
    finally:
        _drop_test_route()
    assert r.status_code == 503 and r.headers["retry-after"] == "2"
    assert "busy" in r.json()["detail"].lower()


def test_database_errors_and_statement_timeouts_return_503():
    client = _client_with_failing_route(OperationalError("SELECT 1", {}, Exception("canceling statement due to statement timeout")))
    try:
        r = client.get("/__test_boom")
    finally:
        _drop_test_route()
    assert r.status_code == 503 and "retry-after" in r.headers


# ------------------------------------------------------------- fewer queries per cover

@pytest.fixture
def cfg_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(AppConfig(key="s3_bucket", value="b1"))
    session.commit()
    app_config.invalidate_app_config_cache()
    yield session
    app_config.invalidate_app_config_cache()


def _count_queries(session, fn):
    from sqlalchemy import event
    n = 0

    def _c(*a, **k):
        nonlocal n
        n += 1

    event.listen(session.get_bind(), "before_cursor_execute", _c)
    try:
        fn()
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", _c)
    return n


def test_storage_settings_are_read_once_not_on_every_call(cfg_db):
    n = _count_queries(cfg_db, lambda: [storage._config_value(cfg_db, "s3_bucket") for _ in range(50)])
    assert n == 1, f"50 lookups should cost 1 query, cost {n}"


def test_changing_a_setting_takes_effect_immediately_in_this_process(cfg_db):
    assert storage._config_value(cfg_db, "s3_bucket") == "b1"
    app_config.set_app_config_value(cfg_db, "s3_bucket", "b2")
    assert storage._config_value(cfg_db, "s3_bucket") == "b2"
    app_config.delete_app_config_key(cfg_db, "s3_bucket")
    assert storage._config_value(cfg_db, "s3_bucket", "fallback") == "fallback"


def test_security_sensitive_settings_bypass_the_cache(cfg_db):
    # public_downloads_enabled and SECRET_KEY are read uncached so a change is seen at once.
    cfg_db.add(AppConfig(key="public_downloads_enabled", value="false"))
    cfg_db.commit()
    assert app_config.get_app_config_value(cfg_db, "public_downloads_enabled") == "false"
    cfg_db.query(AppConfig).filter_by(key="public_downloads_enabled").one().value = "true"
    cfg_db.commit()
    assert app_config.get_app_config_value(cfg_db, "public_downloads_enabled") == "true"


def test_s3_clients_are_built_once_per_configuration(cfg_db, monkeypatch):
    built = []
    fake_boto3 = types.SimpleNamespace(client=lambda service, **kw: built.append(kw) or object())
    fake_config_mod = types.SimpleNamespace(Config=lambda **kw: kw)
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", types.SimpleNamespace(config=fake_config_mod))
    monkeypatch.setitem(sys.modules, "botocore.config", fake_config_mod)
    storage._build_s3_client.cache_clear()
    for key in ("s3_endpoint_url", "s3_region", "s3_access_key_id", "s3_secret_access_key"):
        cfg_db.add(AppConfig(key=key, value=f"v-{key}"))
    cfg_db.commit()
    app_config.invalidate_app_config_cache()

    first = storage._s3_client(cfg_db)
    clients = {id(storage._s3_client(cfg_db)) for _ in range(30)}

    assert len(built) == 1 and clients == {id(first)}, "30 requests must share one client"
    storage._s3_client(cfg_db, endpoint_url_override="https://public.example")
    assert len(built) == 2, "a different endpoint (browser-facing presign URL) gets its own client"
    storage._build_s3_client.cache_clear()
