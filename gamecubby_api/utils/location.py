from typing import Optional
from sqlalchemy.orm import Session
from ..models.location import Location
from ..models.game import Game


def create_location(session: Session, name: str, parent_id: Optional[int] = None,
                    type: Optional[str] = None) -> Location:
    location = Location(name=name, parent_id=parent_id, type=type)
    session.add(location)
    session.commit()
    session.refresh(location)
    return location


def get_location(session: Session, location_id: int) -> Optional[Location]:
    return session.query(Location).filter_by(id=location_id).first()


def list_top_locations(session: Session) -> list[Location]:
    return session.query(Location).filter_by(parent_id=None).order_by(Location.name).all()


def list_child_locations(session: Session, parent_id: int) -> list[Location]:
    return session.query(Location).filter_by(parent_id=parent_id).order_by(Location.name).all()


def list_all_locations(session: Session) -> list[Location]:
    return session.query(Location).order_by(Location.name).all()


def get_location_path(session: Session, game_id: int) -> list[dict]:
    """
    Returns complete location path from root to game's location.
    Guaranteed order: [root, ..., parent, current].
    Returns an empty list if game has no location.
    """
    game = session.query(Game).filter_by(id=game_id).first()
    if not game or not game.location_id:
        return []

    location_ids = []
    current_id = game.location_id

    while current_id:
        location_ids.append(current_id)
        parent = session.query(Location.parent_id).filter_by(id=current_id).first()
        current_id = parent[0] if parent else None

    locations = session.query(Location).filter(Location.id.in_(location_ids)).all()
    loc_dict = {loc.id: loc for loc in locations}

    return [
        {"id": loc.id, "name": loc.name}
        for loc_id in reversed(location_ids)
        if (loc := loc_dict.get(loc_id))
    ]


def get_default_location_id(session: Session) -> Optional[int]:
    default = session.query(Location).filter_by(name="Default Storage").first()
    return default.id if default else None


def delete_location(session: Session, location_id: int) -> bool:
    """
    Delete a location ONLY if:
      - it exists,
      - it has NO child locations,
      - and NO games are assigned to it.

    Returns:
        True  -> deleted
        False -> not deleted (doesn't exist, has children, or has games)
    """
    loc = session.query(Location).filter_by(id=location_id).first()
    if not loc:
        return False

    has_children = session.query(Location.id).filter_by(parent_id=location_id).first() is not None
    if has_children:
        return False

    has_games = session.query(Game.id).filter_by(location_id=location_id).first() is not None
    if has_games:
        return False

    session.delete(loc)
    session.commit()
    return True


def rename_location(session: Session, location_id: int, new_name: str) -> Optional[Location]:
    """
    Rename a location (name only). Returns the updated Location or None if not found.
    Raises ValueError if new_name is empty/whitespace.
    """
    loc = session.query(Location).filter_by(id=location_id).first()
    if not loc:
        return None

    clean = (new_name or "").strip()
    if not clean:
        raise ValueError("Location name cannot be empty")

    loc.name = clean
    session.commit()
    session.refresh(loc)
    return loc


def migrate_location_games(session: Session, source_location_id: int, target_location_id: int) -> int:
    """
    Bulk-migrate all games from source_location_id to target_location_id.

    Returns:
        int -> number of games updated.

    Raises:
        ValueError -> if target location doesn't exist, or source==target.
    """
    if source_location_id == target_location_id:
        raise ValueError("Source and target locations must be different")

    target = session.query(Location.id).filter_by(id=target_location_id).first()
    if not target:
        raise ValueError("Target location does not exist")

    affected = (
        session.query(Game)
        .filter(Game.location_id == source_location_id)
        .update({Game.location_id: target_location_id}, synchronize_session=False)
    )
    session.commit()
    return int(affected or 0)