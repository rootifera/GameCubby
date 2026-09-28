from unittest.mock import MagicMock

from gamecubby_api.utils.rate_limit import client_ip


def _make_request(client_host="1.2.3.4", headers=None):
    req = MagicMock()
    req.client.host = client_host
    req.headers = headers or {}
    return req


def test_client_ip_falls_back_to_direct_connection():
    assert client_ip(_make_request(client_host="10.0.0.1")) == "10.0.0.1"


def test_client_ip_prefers_x_real_ip():
    req = _make_request(client_host="127.0.0.1", headers={"x-real-ip": "203.0.113.5"})
    assert client_ip(req) == "203.0.113.5"


def test_client_ip_falls_back_to_x_forwarded_for_rightmost_address():
    # The rightmost entry is what the trusted proxy appended from the real TCP
    # connection — the client cannot forge it by sending their own XFF header.
    req = _make_request(
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "spoofed-ip, 10.0.0.1, 203.0.113.5"},
    )
    assert client_ip(req) == "203.0.113.5"


def test_client_ip_x_real_ip_takes_priority_over_x_forwarded_for():
    req = _make_request(
        client_host="127.0.0.1",
        headers={"x-real-ip": "203.0.113.5", "x-forwarded-for": "1.1.1.1"},
    )
    assert client_ip(req) == "203.0.113.5"


def test_client_ip_ignores_empty_x_real_ip():
    req = _make_request(
        client_host="10.0.0.2",
        headers={"x-real-ip": "  ", "x-forwarded-for": "1.1.1.1, 203.0.113.9"},
    )
    assert client_ip(req) == "203.0.113.9"


def test_client_ip_handles_none_client_without_crashing():
    req = MagicMock()
    req.client = None
    req.headers = {}
    assert client_ip(req) == ""
