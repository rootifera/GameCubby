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
