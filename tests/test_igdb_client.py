"""IGDB client: honour Retry-After, and recover from a revoked/expired token with one retry."""
import asyncio

import httpx
import pytest

from gamecubby_api.utils import external


class _Client:
    def __init__(self, responses):
        self.responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, **_):
        return self.responses.pop(0)


def _resp(status, **headers):
    return httpx.Response(status, headers=headers, request=httpx.Request("POST", "https://api.igdb.test"), json=[{"id": 1}])


def _run_post(monkeypatch, responses, retries=2):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    shared = list(responses)
    monkeypatch.setattr(external.httpx, "AsyncClient", lambda **_: _Client(shared))
    monkeypatch.setattr(external.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(external, "HTTP_RETRIES", retries)
    result = asyncio.run(external._post_with_retry("https://api.igdb.test"))
    return result, sleeps


def test_retry_after_is_honoured_when_rate_limited(monkeypatch):
    result, sleeps = _run_post(monkeypatch, [_resp(429, **{"Retry-After": "3"}), _resp(200)])
    assert result.status_code == 200 and sleeps == [3.0]


def test_an_excessive_retry_after_is_capped(monkeypatch):
    _, sleeps = _run_post(monkeypatch, [_resp(429, **{"Retry-After": "3600"}), _resp(200)])
    assert sleeps == [external.MAX_RETRY_AFTER_SECONDS]


def test_without_retry_after_the_normal_backoff_is_used(monkeypatch):
    _, sleeps = _run_post(monkeypatch, [_resp(503), _resp(503), _resp(200)])
    assert sleeps == [0.5, 1.0]


def test_a_garbage_retry_after_falls_back_to_backoff(monkeypatch):
    _, sleeps = _run_post(monkeypatch, [_resp(429, **{"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}), _resp(200)])
    assert sleeps == [0.5]


# ---- 401: a revoked token is replaced once

def _setup_token_flow(monkeypatch, outcomes):
    """outcomes: what _post_with_retry does per call: an int status (error) or 'ok'."""
    tokens = iter(["token-old", "token-new", "token-newer"])
    used = []

    async def fake_get_token():
        if external._igdb_token is None:
            external._igdb_token = next(tokens)
        return external._igdb_token

    async def fake_post(url, *, headers=None, data=None, params=None):
        used.append(headers["Authorization"])
        outcome = outcomes.pop(0)
        if outcome == "ok":
            return httpx.Response(200, json=[{"id": 7}], request=httpx.Request("POST", url))
        raise httpx.HTTPStatusError("err", request=httpx.Request("POST", url), response=httpx.Response(outcome, request=httpx.Request("POST", url)))

    monkeypatch.setattr(external, "_get_configured_igdb_credentials", lambda: ("cid", "secret"))
    monkeypatch.setattr(external, "get_igdb_token", fake_get_token)
    monkeypatch.setattr(external, "_post_with_retry", fake_post)
    monkeypatch.setattr(external, "_igdb_token", None)
    return used


def test_a_revoked_token_is_dropped_and_the_request_retried_once(monkeypatch):
    used = _setup_token_flow(monkeypatch, [401, "ok"])
    result = asyncio.run(external._igdb_post("https://api.igdb.com/v4/games", "fields id;"))
    assert result.status_code == 200
    assert used == ["Bearer token-old", "Bearer token-new"], "second attempt must use a freshly fetched token"


def test_a_second_401_is_not_retried_forever(monkeypatch):
    used = _setup_token_flow(monkeypatch, [401, 401, "ok"])
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(external._igdb_post("https://api.igdb.com/v4/games", "fields id;"))
    assert len(used) == 2


def test_other_errors_are_not_treated_as_token_problems(monkeypatch):
    used = _setup_token_flow(monkeypatch, [403, "ok"])
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(external._igdb_post("https://api.igdb.com/v4/games", "fields id;"))
    assert used == ["Bearer token-old"], "a 403 is a permissions problem; a new token won't help"


def test_the_public_functions_use_the_recovering_helper(monkeypatch):
    calls = []

    async def fake_igdb_post(url, data):
        calls.append(url.rsplit("/", 1)[-1])
        return httpx.Response(200, json=[{"id": 1, "name": "Zelda", "company": 5}], request=httpx.Request("POST", url))

    monkeypatch.setattr(external, "_igdb_post", fake_igdb_post)
    asyncio.run(external.fetch_igdb_game(1))
    asyncio.run(external.search_igdb_games("zelda"))
    asyncio.run(external.fetch_igdb_companies([5]))
    assert calls == ["games", "games", "companies"]
