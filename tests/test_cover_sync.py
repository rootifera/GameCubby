import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gamecubby_api.models import Base
from gamecubby_api.models.game import Game
from gamecubby_api.utils import storage


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class _ClientError(Exception):
    """Stand-in for botocore's ClientError (same `.response` shape), so tests don't need boto3."""

    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code, "Message": code}}


def _client_error(code: str) -> _ClientError:
    return _ClientError(code)


class FakeS3:
    """head_object succeeds only for keys in `present`; `errors` maps key -> error code."""

    def __init__(self, present=(), errors=None):
        self.present = set(present)
        self.errors = errors or {}

    def head_object(self, Bucket, Key):
        if Key in self.errors:
            raise _client_error(self.errors[Key])
        if Key not in self.present:
            raise _client_error("404")
        return {}


def _setup_s3(monkeypatch, db, fake, download_ok=True):
    monkeypatch.setattr(storage, "configured_storage_backend", lambda db: "s3")
    monkeypatch.setattr(storage, "_s3_client", lambda db, **kw: fake)
    monkeypatch.setattr(storage, "_s3_bucket", lambda db: "bucket")
    monkeypatch.setattr(storage, "_s3_prefix", lambda db: "")
    downloaded = []

    async def fake_download(db, game):
        downloaded.append(game.id)
        return download_ok and bool(game.cover_url)

    monkeypatch.setattr(storage, "download_and_store_cover", fake_download)
    return downloaded


def _add(db, name, *, igdb_id=0, cover_url="http://x/c.jpg", cached=True):
    g = Game(name=name, igdb_id=igdb_id, cover_url=cover_url, cover_cached=cached)
    db.add(g)
    db.commit()
    return g


def test_deleted_cover_is_detected_and_redownloaded(monkeypatch):
    db = _session()
    present = _add(db, "Present", igdb_id=1)
    deleted = _add(db, "Deleted from bucket", igdb_id=2)
    fresh = _add(db, "Never cached", igdb_id=3, cached=False)
    fake = FakeS3(present={storage._cover_s3_key(db, present)})
    downloaded = _setup_s3(monkeypatch, db, fake)

    result = asyncio.run(storage.sync_all_game_covers(db))

    assert result["already_cached"] == 1
    assert result["missing_in_storage"] == 1
    assert result["cached"] == 2  # the re-downloaded one + the never-cached one
    assert result["failed"] == 0
    assert sorted(downloaded) == sorted([deleted.id, fresh.id])
    db.refresh(deleted)
    assert deleted.cover_cached is True


def test_lost_custom_cover_clears_flag_and_is_reported(monkeypatch):
    db = _session()
    custom = _add(db, "Custom game", igdb_id=0, cover_url=None)  # uploaded cover, no IGDB url
    _setup_s3(monkeypatch, db, FakeS3())

    result = asyncio.run(storage.sync_all_game_covers(db))

    assert result["total"] == 1  # custom games with a cached cover are now examined too
    assert result["missing_in_storage"] == 1
    assert result["failed_game_ids"] == [custom.id]
    db.refresh(custom)
    assert custom.cover_cached is False


def test_failed_redownload_does_not_keep_claiming_a_cover(monkeypatch):
    db = _session()
    game = _add(db, "Deleted", igdb_id=5)
    _setup_s3(monkeypatch, db, FakeS3(), download_ok=False)

    result = asyncio.run(storage.sync_all_game_covers(db))

    assert result["failed_game_ids"] == [game.id]
    db.refresh(game)
    assert game.cover_cached is False


def test_unverifiable_covers_are_left_untouched(monkeypatch):
    db = _session()
    game = _add(db, "Access denied", igdb_id=7)
    key = storage._cover_s3_key(db, game)
    # 403 is what S3 returns for missing keys when the account lacks ListBucket, and
    # what it returns on permission problems: we can't tell, so we must not touch it.
    downloaded = _setup_s3(monkeypatch, db, FakeS3(errors={key: "403"}))

    result = asyncio.run(storage.sync_all_game_covers(db))

    assert result["unverified"] == 1
    assert result["unverified_game_ids"] == [game.id]
    assert result["missing_in_storage"] == 0
    assert downloaded == []
    db.refresh(game)
    assert game.cover_cached is True


def test_local_backend_checks_the_file(monkeypatch, tmp_path):
    db = _session()
    present = _add(db, "Has file", igdb_id=1)
    missing = _add(db, "No file", igdb_id=2)
    paths = {present.id: tmp_path / "p.jpg", missing.id: tmp_path / "m.jpg"}
    paths[present.id].write_bytes(b"x")
    monkeypatch.setattr(storage, "configured_storage_backend", lambda db: "local")
    monkeypatch.setattr(storage, "_cover_local_path", lambda g: paths[g.id])
    downloaded = []

    async def fake_download(db, game):
        downloaded.append(game.id)
        return True

    monkeypatch.setattr(storage, "download_and_store_cover", fake_download)

    result = asyncio.run(storage.sync_all_game_covers(db))

    assert result["already_cached"] == 1
    assert result["missing_in_storage"] == 1
    assert downloaded == [missing.id]


def test_single_cover_check(monkeypatch):
    db = _session()
    game = _add(db, "Single", igdb_id=9)
    key = storage._cover_s3_key(db, game)
    _setup_s3(monkeypatch, db, FakeS3(present={key}))
    assert asyncio.run(storage.cached_cover_exists(db, game)) is True
    _setup_s3(monkeypatch, db, FakeS3())
    assert asyncio.run(storage.cached_cover_exists(db, game)) is False
