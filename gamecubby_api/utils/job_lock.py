"""PostgreSQL advisory locks for work that must have one active owner."""

from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from typing import Iterator

from sqlalchemy import text

from ..db import engine


def _lock_key(name: str) -> int:
    return int.from_bytes(sha256(name.encode("utf-8")).digest()[:8], "big", signed=True)


@contextmanager
def try_job_lock(name: str) -> Iterator[bool]:
    """Hold a session-level PostgreSQL advisory lock for the duration of a job."""
    connection = engine.connect()
    key = _lock_key(name)
    acquired = bool(connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar())
    try:
        yield acquired
    finally:
        if acquired:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
        connection.close()
