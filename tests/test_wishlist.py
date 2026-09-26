import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gamecubby_api.models import Base
from gamecubby_api.models.game import Game
from gamecubby_api.models.platform import Platform
from gamecubby_api.routers import games as games_router
from gamecubby_api.routers import wishlist as wishlist_router
from gamecubby_api.schemas.game import AddGameFromIGDBRequest, GameCreate
from gamecubby_api.schemas.wishlist import WishlistResolveRequest
from gamecubby_api.utils import game as game_utils
from gamecubby_api.utils.game import add_igdb_game_and_resolve_wishlist, create_game_and_resolve_wishlist
from gamecubby_api.utils.wishlist import (
    WishlistAlreadyResolvedError,
    WishlistNotFoundError,
    active_wishlist_ids_for_igdb,
    create_wishlist_item,
    get_wishlist_item,
    list_wishlist_items,
    resolve_wishlist_item,
    update_wishlist_item,
)


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _game(db, name="Library Game", igdb_id=0):
    game = Game(name=name, igdb_id=igdb_id)
    db.add(game)
    db.commit()
    return game


def test_wishlist_item_defaults_to_active_and_keeps_platforms_and_links():
    db = _session()
    db.add_all([Platform(id=6, name="PC"), Platform(id=48, name="PlayStation 4")])
    db.commit()
    item = create_wishlist_item(db, {
        "igdb_id": 7346, "name": "Example Game", "release_year": 2024,
        "cover_url": "https://images.example.test/cover.jpg", "platform_ids": [48, 6],
        "links": [{"label": "eBay", "url": "https://example.test/ebay"}],
    })
    assert item.status == "active"
    assert item.library_game_id is None
    assert [platform.id for platform in item.platforms] == [6, 48]
    assert [(link.label, link.url) for link in item.links] == [("eBay", "https://example.test/ebay")]


def test_resolving_wishlist_item_records_library_game_and_filters_default_list():
    db = _session()
    active = create_wishlist_item(db, {"name": "Still Wanted"})
    resolved = create_wishlist_item(db, {"name": "Already Owned"})
    game = _game(db)
    updated = resolve_wishlist_item(db, resolved.id, game.id)
    assert updated.status == "in_library"
    assert updated.library_game_id == game.id
    assert [item.id for item in list_wishlist_items(db)] == [active.id]
    assert {item.id for item in list_wishlist_items(db, include_resolved=True)} == {active.id, resolved.id}
    assert [item.id for item in list_wishlist_items(db, status="in_library")] == [resolved.id]


def test_resolve_rejects_missing_library_game_and_already_resolved_item():
    db = _session()
    item = create_wishlist_item(db, {"name": "Example Game"})
    with pytest.raises(ValueError, match="Library game not found"):
        resolve_wishlist_item(db, item.id, 999)
    assert get_wishlist_item(db, item.id).status == "active"
    game = _game(db)
    resolve_wishlist_item(db, item.id, game.id)
    with pytest.raises(WishlistAlreadyResolvedError):
        resolve_wishlist_item(db, item.id, game.id)
    with pytest.raises(WishlistNotFoundError):
        resolve_wishlist_item(db, 999, game.id)


def test_resolve_endpoint_returns_not_found_and_conflict_errors():
    db = _session()
    game = _game(db)
    with pytest.raises(HTTPException) as missing:
        wishlist_router.resolve_item(999, WishlistResolveRequest(game_id=game.id), db)
    assert missing.value.status_code == 404
    item = create_wishlist_item(db, {"name": "Example Game"})
    resolve_wishlist_item(db, item.id, game.id)
    with pytest.raises(HTTPException) as resolved:
        wishlist_router.resolve_item(item.id, WishlistResolveRequest(game_id=game.id), db)
    assert resolved.value.status_code == 409


def test_wishlist_update_replaces_links_and_rejects_missing_platforms():
    db = _session()
    db.add(Platform(id=6, name="PC"))
    db.commit()
    item = create_wishlist_item(db, {"name": "Example Game"})
    updated = update_wishlist_item(db, item.id, {
        "platform_ids": [6], "links": [{"label": "Shop", "url": "https://example.test/shop"}],
    })
    assert [platform.id for platform in updated.platforms] == [6]
    assert [link.label for link in updated.links] == ["Shop"]
    with pytest.raises(ValueError, match="999"):
        update_wishlist_item(db, item.id, {"platform_ids": [999]})


def test_manual_game_creation_with_wishlist_resolves_in_one_transaction():
    db = _session()
    item = create_wishlist_item(db, {"name": "Example Game"})
    game = create_game_and_resolve_wishlist(db, {"name": "Example Game"}, item.id)
    assert game.id is not None
    updated = get_wishlist_item(db, item.id)
    assert updated.status == "in_library"
    assert updated.library_game_id == game.id


def test_manual_game_endpoint_resolves_wishlist_and_rolls_back_on_resolution_failure():
    db = _session()
    item = create_wishlist_item(db, {"name": "Example Game"})

    created = games_router.add_game(GameCreate(name="Example Game", wishlist_id=item.id), db)

    assert created.id is not None
    assert get_wishlist_item(db, item.id).library_game_id == created.id
    before = db.query(Game).count()
    with pytest.raises(HTTPException) as error:
        games_router.add_game(GameCreate(name="Should Roll Back", wishlist_id=999), db)
    assert error.value.status_code == 404
    assert db.query(Game).count() == before


def test_failed_manual_game_creation_does_not_resolve_wishlist_item(monkeypatch):
    db = _session()
    item = create_wishlist_item(db, {"name": "Example Game"})

    def fail_create(*_args, **_kwargs):
        raise RuntimeError("creation failed")

    monkeypatch.setattr(game_utils, "create_game", fail_create)
    with pytest.raises(RuntimeError, match="creation failed"):
        create_game_and_resolve_wishlist(db, {"name": "Example Game"}, item.id)
    assert get_wishlist_item(db, item.id).status == "active"


def test_failed_wishlist_resolution_rolls_back_manual_game_creation():
    db = _session()
    before = db.query(Game).count()
    with pytest.raises(WishlistNotFoundError):
        create_game_and_resolve_wishlist(db, {"name": "Example Game"}, 999)
    assert db.query(Game).count() == before


def test_igdb_game_creation_with_wishlist_resolves_in_one_transaction(monkeypatch):
    db = _session()
    item = create_wishlist_item(db, {"name": "Example Game", "igdb_id": 7346})

    async def fake_add(session, **_kwargs):
        game = Game(name="Example Game", igdb_id=7346)
        session.add(game)
        session.flush()
        return game

    monkeypatch.setattr(game_utils, "add_game_from_igdb", fake_add)
    game = asyncio.run(add_igdb_game_and_resolve_wishlist(
        db, wishlist_id=item.id, igdb_id=7346, platform_ids=[]
    ))
    assert game.id is not None
    assert get_wishlist_item(db, item.id).library_game_id == game.id


def test_igdb_game_endpoint_resolves_wishlist_atomically(monkeypatch):
    db = _session()
    item = create_wishlist_item(db, {"name": "Example Game", "igdb_id": 7346})

    async def fake_add(session, **_kwargs):
        game = Game(name="Example Game", igdb_id=7346)
        session.add(game)
        session.flush()
        return game

    monkeypatch.setattr(game_utils, "add_game_from_igdb", fake_add)
    created = asyncio.run(games_router.add_game_from_igdb_endpoint(
        AddGameFromIGDBRequest(igdb_id=7346, platform_ids=[], wishlist_id=item.id), db
    ))

    assert created.id is not None
    assert get_wishlist_item(db, item.id).library_game_id == created.id


def test_exact_igdb_matching_is_advisory_and_name_only_never_resolves():
    db = _session()
    matching = create_wishlist_item(db, {"name": "Same Name", "igdb_id": 7346})
    name_only = create_wishlist_item(db, {"name": "Same Name"})
    _game(db, name="Same Name", igdb_id=7346)
    assert active_wishlist_ids_for_igdb(db, 7346) == [matching.id]
    assert get_wishlist_item(db, matching.id).status == "active"
    assert get_wishlist_item(db, name_only.id).status == "active"


def test_regular_igdb_game_creation_exposes_exact_active_wishlist_matches(monkeypatch):
    db = _session()
    matching = create_wishlist_item(db, {"name": "Example Game", "igdb_id": 7346})
    resolved = create_wishlist_item(db, {"name": "Old Copy", "igdb_id": 7346})
    resolve_wishlist_item(db, resolved.id, _game(db).id)

    async def fake_add(session, **_kwargs):
        game = Game(name="Example Game", igdb_id=7346)
        session.add(game)
        session.commit()
        return game

    monkeypatch.setattr(games_router, "add_game_from_igdb", fake_add)
    created = asyncio.run(games_router.add_game_from_igdb_endpoint(
        AddGameFromIGDBRequest(igdb_id=7346, platform_ids=[]), db
    ))

    assert created.matching_wishlist_ids == [matching.id]
    assert get_wishlist_item(db, matching.id).status == "active"
