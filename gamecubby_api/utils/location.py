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

def get_location_path(session: Session, game_id: int) -> list[int]:
    """
    Given a game ID, return the full path of locations (from top-level to bottom-level).
    The path will be a list of location IDs.
    """
    path_ids = []

    game = session.query(Game).filter_by(id=game_id).first()
    if not game or not game.location_id:
        return path_ids

    current = session.query(Location).filter_by(id=game.location_id).first()

    while current:
        path_ids.insert(0, current.id)
        if current.parent_id:
            current = session.query(Location).filter_by(id=current.parent_id).first()
        else:
            current = None

    return path_ids