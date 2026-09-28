import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gamecubby_api.models import Base
from gamecubby_api.models.game import Game
from gamecubby_api.utils import game as game_utils
from gamecubby_api.utils import storage


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_metadata_update_status_detects_an_igdb_change_without_mutating_game(monkeypatch):
    db = _session()
    game = Game(name="Stored name", igdb_id=42, updated_at=100)
    db.add(game)
    db.commit()

    async def fetch_game(_igdb_id):
        return {"id": 42, "updated_at": 200, "name": "Changed name"}

    monkeypatch.setattr(game_utils, "fetch_igdb_game", fetch_game)
    checked_game, status = asyncio.run(game_utils.get_game_metadata_update_status(db, game.id))

    assert checked_game.id == game.id
    assert status == {
        "game_id": game.id,
        "igdb_id": 42,
        "checked": True,
        "update_available": True,
        "local_updated_at": 100,
        "igdb_updated_at": 200,
        "message": "Metadata update available from IGDB.",
    }
    db.refresh(game)
    assert game.name == "Stored name"
    assert game.updated_at == 100


def test_metadata_update_status_reports_current_and_non_igdb_games(monkeypatch):
    db = _session()
    current = Game(name="Current", igdb_id=7, updated_at=200)
    custom = Game(name="Custom", igdb_id=0, updated_at=None)
    db.add_all([current, custom])
    db.commit()

    async def fetch_game(_igdb_id):
        return {"id": 7, "updated_at": 200}

    monkeypatch.setattr(game_utils, "fetch_igdb_game", fetch_game)
    _, current_status = asyncio.run(game_utils.get_game_metadata_update_status(db, current.id))
    _, custom_status = asyncio.run(game_utils.get_game_metadata_update_status(db, custom.id))

    assert current_status["checked"] is True
    assert current_status["update_available"] is False
    assert current_status["message"] == "Already up to date."
    assert custom_status["checked"] is False
    assert custom_status["update_available"] is False
    assert custom_status["message"] == "Game has no IGDB ID (not an IGDB-backed game)."


def test_cover_sync_reports_failed_game_ids(monkeypatch):
    db = _session()
    cached = Game(name="Cached", cover_url="https://example.test/cached.jpg")
    stored = Game(name="Stored", cover_url="https://example.test/stored.jpg")
    failed = Game(name="Failed", cover_url="https://example.test/failed.jpg")
    db.add_all([cached, stored, failed])
    db.commit()

    monkeypatch.setattr(storage, "has_cached_game_cover", lambda _db, game: game.id == cached.id)

    async def cache_cover(_db, game):
        return game.id == stored.id

    monkeypatch.setattr(storage, "cache_game_cover", cache_cover)
    result = asyncio.run(storage.sync_all_game_covers(db))

    assert result == {
        "total": 3,
        "cached": 1,
        "already_cached": 1,
        "failed": 1,
        "failed_game_ids": [failed.id],
    }
