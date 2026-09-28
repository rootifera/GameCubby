import asyncio

import httpx
import pytest

from gamecubby_api.utils import external


class _Client:
    def __init__(self, action):
        self.action = action

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, *_args, **_kwargs):
        return self.action()


def test_post_retries_transient_transport_errors(monkeypatch):
    attempts = 0

    def action():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary outage")
        return httpx.Response(200, request=httpx.Request("POST", "https://example.test"))

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(external.httpx, "AsyncClient", lambda **_: _Client(action))
    monkeypatch.setattr(external.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(external, "HTTP_RETRIES", 2)

    response = asyncio.run(external._post_with_retry("https://example.test"))

    assert response.status_code == 200
    assert attempts == 2


def test_post_does_not_retry_non_transient_http_errors(monkeypatch):
    attempts = 0

    def action():
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, request=httpx.Request("POST", "https://example.test"))

    monkeypatch.setattr(external.httpx, "AsyncClient", lambda **_: _Client(action))
    monkeypatch.setattr(external, "HTTP_RETRIES", 2)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(external._post_with_retry("https://example.test"))
    assert attempts == 1


def test_empty_company_requests_do_not_need_credentials(monkeypatch):
    def no_credentials():
        raise AssertionError("credentials should not be read for an empty request")

    monkeypatch.setattr(external, "_get_configured_igdb_credentials", no_credentials)

    assert asyncio.run(external.fetch_igdb_companies([])) == {}
    assert asyncio.run(external.fetch_igdb_involved_companies([])) == []


def test_concurrent_token_refresh_only_calls_twitch_once(monkeypatch):
    """Under lock, only one coroutine should fetch a new token even when many fire simultaneously."""
    call_count = 0

    def fake_credentials():
        return "client-id", "client-secret"

    async def fake_post(url, *, headers=None, data=None, params=None):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0)  # yield so other coroutines can reach the lock
        resp = httpx.Response(
            200,
            json={"access_token": "test-token", "expires_in": 3600},
            request=httpx.Request("POST", url),
        )
        return resp

    monkeypatch.setattr(external, "_get_configured_igdb_credentials", fake_credentials)
    monkeypatch.setattr(external, "_post_with_retry", fake_post)
    # Force token expiry so all coroutines see a stale cache.
    monkeypatch.setattr(external, "_igdb_token", None)
    monkeypatch.setattr(external, "_igdb_token_expiry", 0.0)
    # Reset the shared module-level lock so this test is self-contained.
    monkeypatch.setattr(external, "_igdb_token_lock", asyncio.Lock())

    async def run():
        tokens = await asyncio.gather(*[external.get_igdb_token() for _ in range(10)])
        return tokens

    tokens = asyncio.run(run())

    assert all(t == "test-token" for t in tokens)
    assert call_count == 1, f"Expected 1 Twitch call, got {call_count}"
