"""
Bulk metadata refresh: a failure must never leave games worse off. (Force refresh used to zero every
game's updated_at BEFORE contacting IGDB, so an IGDB outage flagged the whole library as outdated.)
"""
import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from gamecubby_api.models import Base
from gamecubby_api.models.game import Game
from gamecubby_api.utils import game as game_utils


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    real_sleep = asyncio.sleep

    async def fast_sleep(delay, *a, **k):
        await real_sleep(0)

    monkeypatch.setattr(game_utils.asyncio, "sleep", fast_sleep)


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _library(db, n=3, stamp=1000):
    games = [Game(name=f"Game {i}", igdb_id=100 + i, updated_at=stamp, cover_url="http://x/c.jpg") for i in range(n)]
    db.add_all(games)
    db.commit()
    return games


def _igdb_ok(monkeypatch, igdb_stamp=1000, name="Renamed by IGDB"):
    async def fake_fetch(igdb_id):
        return {"updated_at": igdb_stamp, "rating": 80}

    monkeypatch.setattr(game_utils, "fetch_igdb_game", fake_fetch)
    monkeypatch.setattr(game_utils, "format_igdb_game", lambda raw, db: {
        "name": name, "summary": "s", "release_date": 1999, "cover_url": "http://x/c.jpg",
        "genres": [], "game_modes": [],
    })


def test_force_refresh_with_igdb_down_changes_nothing(monkeypatch):
    db = _session()
    _library(db, 3, stamp=1000)

    async def igdb_down(igdb_id):
        raise RuntimeError("IGDB request failed after 4 attempts")

    monkeypatch.setattr(game_utils, "fetch_igdb_game", igdb_down)

    result = game_utils.force_refresh_metadata(db)

    assert result == {"updated": 0, "skipped": 0, "errors": 3}
    assert [g.updated_at for g in db.query(Game).order_by(Game.id)] == [1000, 1000, 1000], \
        "a failed force refresh must not touch the stored timestamps"


def test_force_refresh_reapplies_metadata_even_when_timestamps_match(monkeypatch):
    db = _session()
    _library(db, 2, stamp=1000)
    _igdb_ok(monkeypatch, igdb_stamp=1000, name="Fresh from IGDB")

    normal = game_utils.refresh_all_games_metadata(db)
    assert normal == {"updated": 0, "skipped": 2, "errors": 0}
    assert db.query(Game).first().name != "Fresh from IGDB"

    forced = game_utils.force_refresh_metadata(db)
    assert forced == {"updated": 2, "skipped": 0, "errors": 0}
    assert {g.name for g in db.query(Game)} == {"Fresh from IGDB"}
    assert {g.updated_at for g in db.query(Game)} == {1000}, "real timestamps are kept, never zeroed"


def test_one_games_database_error_does_not_poison_the_games_after_it(monkeypatch):
    db = _session()
    games = _library(db, 3, stamp=1000)
    first_id = games[0].id
    calls = []

    async def flaky_refresh(session, game_id, *, force=False):
        calls.append(game_id)
        if game_id == first_id:
            session.add(Game(name=None, igdb_id=1))  # NOT NULL violation: breaks the session when flushed
            session.query(Game).count()
        game = session.query(Game).filter_by(id=game_id).one()
        game.updated_at = 2000
        session.commit()
        return game, True, "Game metadata updated from IGDB."

    monkeypatch.setattr(game_utils, "refresh_game_metadata", flaky_refresh)

    result = game_utils.refresh_all_games_metadata(db)

    assert calls == [g.id for g in games]
    assert result == {"updated": 2, "skipped": 0, "errors": 1}, "only the failing game is lost"
    assert [g.updated_at for g in db.query(Game).order_by(Game.id)] == [1000, 2000, 2000]


def test_the_transaction_is_ended_after_each_game(monkeypatch):
    db = _session()
    _library(db, 3)
    _igdb_ok(monkeypatch, igdb_stamp=1000)
    open_during_next = []

    real = game_utils.refresh_game_metadata

    async def spy(session, game_id, *, force=False):
        open_during_next.append(session.in_transaction())  # state when the NEXT game starts
        return await real(session, game_id, force=force)

    monkeypatch.setattr(game_utils, "refresh_game_metadata", spy)
    game_utils.refresh_all_games_metadata(db)

    assert open_during_next == [False, False, False], "no transaction may be left open between games"
    assert not db.in_transaction()


def test_a_single_game_refresh_is_not_forced_by_default(monkeypatch):
    db = _session()
    game = _library(db, 1, stamp=1000)[0]
    _igdb_ok(monkeypatch, igdb_stamp=1000, name="Should not apply")

    _, updated, message = asyncio.run(game_utils.refresh_game_metadata(db, game.id))

    assert updated is False and "up to date" in message.lower()
    assert db.get(Game, game.id).name == "Game 0"
