"""
Blocking work (S3 uploads, pg_dump, ...) must never run on the event loop: while it
runs, every other request on the worker would hang. These tests run a slow, *blocking*
fake S3 call next to a ticker coroutine and check the ticker kept running.
"""
import asyncio
import inspect
import io
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers, UploadFile

from gamecubby_api.models import Base
from gamecubby_api.models.game import Game
from gamecubby_api.models.storage import FileCategory
from gamecubby_api.routers import backups, search
from gamecubby_api.routers import storage as storage_router
from gamecubby_api.utils import storage

BLOCK_SECONDS = 0.5


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class SlowS3:
    """Blocking (time.sleep) stand-in for a boto3 client."""

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
        time.sleep(BLOCK_SECONDS)

    def put_object(self, **kwargs):
        time.sleep(BLOCK_SECONDS)


async def _run_with_ticker(coro):
    """Run `coro` while counting how often the event loop gets to run other work."""
    ticks = 0
    stop = False

    async def ticker():
        nonlocal ticks
        while not stop:
            await asyncio.sleep(0.01)
            ticks += 1

    t = asyncio.create_task(ticker())
    started = time.perf_counter()
    result = await coro
    elapsed = time.perf_counter() - started
    stop = True
    await t
    return result, ticks, elapsed


def _patch_s3(monkeypatch):
    monkeypatch.setattr(storage, "configured_storage_backend", lambda db: "s3")
    monkeypatch.setattr(storage, "_s3_client", lambda db, **kw: SlowS3())
    monkeypatch.setattr(storage, "_s3_bucket", lambda db: "bucket")
    monkeypatch.setattr(storage, "_s3_prefix", lambda db: "")


def test_s3_file_upload_does_not_block_the_event_loop(monkeypatch):
    db = _session()
    game = Game(name="Big ISO game", igdb_id=1)
    db.add(game)
    db.commit()
    _patch_s3(monkeypatch)
    upload = UploadFile(io.BytesIO(b"x" * 1024), filename="game.iso", headers=Headers({"content-type": "application/octet-stream"}))

    record, ticks, elapsed = asyncio.run(_run_with_ticker(
        storage.upload_and_register_file(db, game, upload, "ISO", "game.iso", category=list(FileCategory)[0])
    ))

    assert record.storage_backend == "s3"
    assert elapsed >= BLOCK_SECONDS
    # ~50 ticks are possible in 0.5 s; a blocked loop manages 0-1.
    assert ticks >= 20, f"event loop was blocked during the S3 upload (only {ticks} ticks)"


def test_s3_cover_write_does_not_block_the_event_loop(monkeypatch):
    db = _session()
    game = Game(name="Cover game", igdb_id=2)
    db.add(game)
    db.commit()
    _patch_s3(monkeypatch)

    _, ticks, elapsed = asyncio.run(_run_with_ticker(storage._store_cover_bytes(db, game, b"jpegbytes")))

    assert elapsed >= BLOCK_SECONDS
    assert ticks >= 20, f"event loop was blocked during the cover write (only {ticks} ticks)"


def test_heavy_endpoints_run_in_the_thread_pool_not_on_the_loop():
    # `def` handlers are run in FastAPI's thread pool; `async def` ones run on the loop.
    heavy = [
        backups.backup_database,
        backups.backup_list,
        backups.backup_sync_storage,
        backups.backup_save_to_disk,
        search.basic_search,
        storage_router.download_file,
    ]
    for handler in heavy:
        assert not inspect.iscoroutinefunction(handler), f"{handler.__name__} would block the event loop"
