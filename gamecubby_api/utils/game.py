from sqlalchemy.orm import Session
from ..models.game import Game

def list_games(session: Session):
    return session.query(Game).order_by(Game.name).all()

def get_game(session: Session, game_id: int):
    return session.query(Game).filter_by(id=game_id).first()

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