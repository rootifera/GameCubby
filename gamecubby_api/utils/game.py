from sqlalchemy.orm import Session

from .location import get_location_path
from ..models.game import Game
from ..utils.external import fetch_igdb_game, fetch_igdb_collection
from ..utils.platform import upsert_platform
from ..utils.collection import create_collection
from ..models.game import Game
from ..models.platform import Platform
from ..models.tag import Tag
from ..models.collection import Collection
from sqlalchemy.orm import selectinload

def get_game(session, game_id):
    game = (
        session.query(Game)
        .options(
            selectinload(Game.platforms),
            selectinload(Game.tags),
            selectinload(Game.collection),
        )
        .filter_by(id=game_id)
        .first()
    )
    if game:
        game.location_path = get_location_path(session, game_id)
    return game

def list_games(session):
    games = (
        session.query(Game)
        .options(
            selectinload(Game.platforms),
            selectinload(Game.tags),
            selectinload(Game.collection),
        )
        .all()
    )
    for game in games:
        game.location_path = get_location_path(session, game.id)
    return games

def create_game(session: Session, game_data: dict):
    from ..models.game import Game
    game = Game(**game_data)
    session.add(game)
    session.commit()
    session.refresh(game)
    return game

def update_game(session: Session, game_id: int, game_data: dict):
    from ..models.game import Game
    game = session.query(Game).filter_by(id=game_id).first()
    if not game:
        return None
    for key, value in game_data.items():
        if value is not None:
            setattr(game, key, value)
    session.commit()
    session.refresh(game)
    return game

def delete_game(session: Session, game_id: int):
    from ..models.game import Game
    game = session.query(Game).filter_by(id=game_id).first()
    if not game:
        return False
    session.delete(game)
    session.commit()
    return True

def list_games_by_tag(session: Session, tag_id: int):
    from ..models.game import Game
    from ..models.game_tag import game_tags
    return (
        session.query(Game)
        .join(game_tags, Game.id == game_tags.c.game_id)
        .filter(game_tags.c.tag_id == tag_id)
        .order_by(Game.name)
        .all()
    )

def list_games_by_platform(session: Session, platform_id: int):
    from ..models.game import Game
    from ..models.game_platform import game_platforms
    return (
        session.query(Game)
        .join(game_platforms, Game.id == game_platforms.c.game_id)
        .filter(game_platforms.c.platform_id == platform_id)
        .order_by(Game.name)
        .all()
    )

def list_games_by_location(session: Session, location_id: int):
    from ..models.game import Game
    return (
        session.query(Game)
        .filter(Game.location_id == location_id)
        .order_by(Game.name)
        .all()
    )


def upsert_collection(session, collection_obj):
    existing = session.query(Collection).filter_by(igdb_id=collection_obj["id"]).first()
    if not existing:
        existing = session.query(Collection).filter_by(name=collection_obj["name"]).first()
    if existing:
        return existing
    return create_collection(session, {"igdb_id": collection_obj["id"], "name": collection_obj["name"]})

async def add_game_from_igdb(
    session,
    igdb_id: int,
    platform_ids: list[int],
    location_id: int | None = None,
    tag_ids: list[int] = [],
    condition: int | None = None,
    order: int | None = None
):
    from ..utils.formatting import format_igdb_game

    raw = await fetch_igdb_game(igdb_id)
    if not raw:
        return None

    game_data = format_igdb_game(raw)
    name = game_data["name"]
    summary = game_data["summary"]
    release_date = game_data["release_date"]
    cover_url = game_data["cover_url"]

    collection_list = await fetch_igdb_collection(igdb_id)
    collection_id = None
    collection = None
    first_collection = collection_list[0] if collection_list else None

    if first_collection:
        collection = upsert_collection(session, first_collection)
        collection_id = collection.id

    game = Game(
        igdb_id=igdb_id,
        name=name,
        summary=summary,
        release_date=release_date,
        cover_url=cover_url,
        location_id=location_id,
        condition=condition,
        order=order,
        collection_id=collection_id,
    )
    session.add(game)

    igdb_platforms = {p["id"]: p for p in game_data.get("platforms", [])}
    for platform_id in platform_ids:
        platform = session.query(Platform).filter_by(id=platform_id).first()
        if not platform and platform_id in igdb_platforms:
            platform = upsert_platform(session, igdb_platforms[platform_id])
        if platform and platform not in game.platforms:
            game.platforms.append(platform)

    for tag_id in tag_ids:
        tag = session.query(Tag).filter_by(id=tag_id).first()
        if tag and tag not in game.tags:
            game.tags.append(tag)

    session.commit()
    session.refresh(game)
    return game