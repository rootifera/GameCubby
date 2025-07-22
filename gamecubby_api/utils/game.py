from sqlalchemy.orm import Session
from .location import get_location_path
from ..models.location import Location
from ..utils.external import fetch_igdb_game, fetch_igdb_collection
from ..utils.platform import upsert_platform
from ..utils.collection import create_collection
from ..models.game import Game
from ..models.tag import Tag
from ..models.collection import Collection
from ..models.mode import Mode
from ..models.platform import Platform
from ..models.genre import Genre
from sqlalchemy.orm import selectinload
from typing import List, Optional


def get_game(session: Session, game_id: int) -> Optional[Game]:
    game = (
        session.query(Game)
        .options(
            selectinload(Game.platforms),
            selectinload(Game.tags),
            selectinload(Game.collection)
        )
        .filter_by(id=game_id)
        .first()
    )

    if game:
        game.location_path = [
            {"id": str(loc["id"]), "name": loc["name"]}
            for loc in get_location_path(session, game.id)
        ]

    return game


def list_games(session: Session) -> List[Game]:
    games = (
        session.query(Game)
        .options(
            selectinload(Game.platforms),
            selectinload(Game.tags),
            selectinload(Game.collection)
        )
        .all()
    )

    location_ids = set()
    for game in games:
        if game.location_id:
            current_id = game.location_id
            while current_id:
                location_ids.add(current_id)
                loc = session.query(Location.parent_id).filter_by(id=current_id).first()
                current_id = loc[0] if loc else None

    locations = (
        session.query(Location)
        .filter(Location.id.in_(location_ids))
        .all()
    ) if location_ids else []

    loc_dict = {loc.id: loc for loc in locations}

    for game in games:
        game.location_path = []
        current_id = game.location_id

        while current_id in loc_dict:
            loc = loc_dict[current_id]
            game.location_path.insert(0, {
                "id": str(loc.id),
                "name": loc.name
            })
            current_id = loc.parent_id

    return games


def create_game(session: Session, game_data: dict):
    from ..models.mode import Mode
    from ..models.platform import Platform
    from ..models.genre import Genre

    mode_ids = game_data.pop("mode_ids", [])
    platform_ids = game_data.pop("platform_ids", [])
    genre_ids = game_data.pop("genre_ids", [])
    game_data['igdb_id'] = 0
    game = Game(**game_data)
    session.add(game)

    if mode_ids:
        modes = session.query(Mode).filter(Mode.id.in_(mode_ids)).all()
        for mode in modes:
            if mode not in game.modes:
                game.modes.append(mode)

    if platform_ids:
        platforms = session.query(Platform).filter(Platform.id.in_(platform_ids)).all()
        for platform in platforms:
            if platform not in game.platforms:
                game.platforms.append(platform)

    if genre_ids:
        genres = session.query(Genre).filter(Genre.id.in_(genre_ids)).all()
        for genre in genres:
            if genre not in game.genres:
                game.genres.append(genre)

    session.commit()
    session.refresh(game)
    return game


def update_game(session: Session, game_id: int, update_data: dict) -> Optional[Game]:
    game = session.query(Game).filter_by(id=game_id).first()
    if not game:
        return None

    if game.igdb_id != 0:
        allowed_fields = {"location_id", "order"}
        if not all(k in allowed_fields for k in update_data.keys()):
            raise ValueError("Cannot update IGDB-sourced games except location/order")

    update_data.pop('igdb_id', None)

    mode_ids = update_data.pop("mode_ids", None)
    if mode_ids is not None:
        game.modes = []
        modes = session.query(Mode).filter(Mode.id.in_(mode_ids)).all()
        for mode in modes:
            game.modes.append(mode)

    platform_ids = update_data.pop("platform_ids", None)
    if platform_ids is not None:
        game.platforms = []
        platforms = session.query(Platform).filter(Platform.id.in_(platform_ids)).all()
        for platform in platforms:
            game.platforms.append(platform)

    genre_ids = update_data.pop("genre_ids", None)
    if genre_ids is not None:
        game.genres = []
        genres = session.query(Genre).filter(Genre.id.in_(genre_ids)).all()
        for genre in genres:
            game.genres.append(genre)

    for key, value in update_data.items():
        if value is not None:
            setattr(game, key, value)

    session.commit()
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
    from ..models.mode import Mode
    from ..utils.mode import upsert_mode
    from ..models.genre import Genre
    from ..models.platform import Platform
    from ..utils.platform import upsert_platform
    from ..models.tag import Tag
    from ..models.collection import Collection

    raw = await fetch_igdb_game(igdb_id)
    if not raw:
        return None

    game_data = format_igdb_game(raw, session)
    name = game_data["name"]
    summary = game_data["summary"]
    release_date = game_data["release_date"]
    cover_url = game_data["cover_url"]

    collection_list = await fetch_igdb_collection(igdb_id)
    collection_id = None
    if collection_list:
        collection_data = collection_list[0]
        collection = session.query(Collection).filter_by(igdb_id=collection_data["id"]).first()
        if not collection:
            collection = Collection(igdb_id=collection_data["id"], name=collection_data["name"])
            session.add(collection)
            session.commit()
            session.refresh(collection)
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

    mode_items = game_data.get("game_modes", [])
    if mode_items:
        for mode_item in mode_items:
            mode_id = mode_item["id"] if isinstance(mode_item, dict) else mode_item
            mode_name = mode_item.get("name") if isinstance(mode_item, dict) else ""
            mode = session.query(Mode).filter_by(id=mode_id).first()
            if not mode:
                mode = upsert_mode(session, mode_id, mode_name or "")
            if mode and mode not in game.modes:
                game.modes.append(mode)

    genre_items = game_data.get("genres", [])
    if genre_items:
        for genre_item in genre_items:
            genre_id = genre_item["id"] if isinstance(genre_item, dict) else genre_item
            genre = session.query(Genre).filter_by(id=genre_id).first()
            if genre and genre not in game.genres:
                game.genres.append(genre)

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
