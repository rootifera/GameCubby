from sqlalchemy.orm import Session
from sqlalchemy import select, insert, delete
from ..models.game_platform import game_platforms
from ..models.game import Game
from ..models.platform import Platform


def attach_platform(session: Session, game_id: int, platform_id: int) -> bool:
    game = session.query(Game).filter_by(id=game_id).first()
    platform = session.query(Platform).filter_by(id=platform_id).first()
    if not game or not platform:
        return False

    exists = session.execute(
        select(game_platforms).where(
            game_platforms.c.game_id == game_id,
            game_platforms.c.platform_id == platform_id,
        )
    ).first()

    if exists:
        return True

    session.execute(
        insert(game_platforms).values(game_id=game_id, platform_id=platform_id)
    )
    session.commit()
    return True


def detach_platform(session: Session, game_id: int, platform_id: int) -> bool:
    session.execute(
        delete(game_platforms).where(
            game_platforms.c.game_id == game_id,
            game_platforms.c.platform_id == platform_id,
        )
    )
    session.commit()
    return True


def list_platforms_for_game(session: Session, game_id: int) -> list[Platform]:
    return (
        session.query(Platform)
        .join(game_platforms, Platform.id == game_platforms.c.platform_id)
        .filter(game_platforms.c.game_id == game_id)
        .order_by(Platform.name)
        .all()
    )
