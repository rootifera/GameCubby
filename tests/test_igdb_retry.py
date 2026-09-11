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
