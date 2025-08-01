from sqlalchemy.orm import Session
from ..models.location import Location
from ..models.game import Game


def create_location(session: Session, name: str, parent_id: int = None, type: str = None):
    location = Location(name=name, parent_id=parent_id, type=type)
    session.add(location)
    session.commit()
    session.refresh(location)
    return location


def get_location(session: Session, location_id: int):
    return session.query(Location).filter_by(id=location_id).first()


def list_top_locations(session: Session):
    """List all locations that have no parent (top level)."""
    return session.query(Location).filter_by(parent_id=None).order_by(Location.name).all()


def list_child_locations(session: Session, parent_id: int):
    """List all direct children of a parent location."""
    return session.query(Location).filter_by(parent_id=parent_id).order_by(Location.name).all()


def list_all_locations(session: Session):
    """List all locations in the system."""
    return session.query(Location).order_by(Location.name).all()


def get_location_path(session: Session, game_id: int) -> list[dict]:
    """
    Returns complete location path from root to game's location.
    Guaranteed order: [root, ..., parent, current]
    Empty list if game has no location.
    """
    path = []
    game = session.query(Game).filter_by(id=game_id).first()

    if not game or not game.location_id:
        return path

    current_id = game.location_id
    location_ids = []
    while current_id:
        location_ids.append(current_id)
        loc = session.query(Location.parent_id).filter_by(id=current_id).first()
        current_id = loc[0] if loc else None

    locations = session.query(Location).filter(Location.id.in_(location_ids)).all()
    loc_dict = {loc.id: loc for loc in locations}

    path = [
        {"id": loc.id, "name": loc.name}
        for loc_id in reversed(location_ids)
        if (loc := loc_dict.get(loc_id))
    ]

    return path


def get_default_location_id(session: Session) -> int | None:
    default = session.query(Location).filter_by(name="Default Storage").first()
    return default.id if default else None
