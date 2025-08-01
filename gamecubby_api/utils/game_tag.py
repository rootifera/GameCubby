from sqlalchemy.orm import Session
from sqlalchemy import select, insert, delete
from ..models.game_tag import game_tags
from ..models.game import Game
from ..models.tag import Tag


def attach_tag(session: Session, game_id: int, tag_id: int) -> bool:
    game = session.query(Game).filter_by(id=game_id).first()
    tag = session.query(Tag).filter_by(id=tag_id).first()
    if not game or not tag:
        return False

    exists = session.execute(
        select(game_tags).where(
            game_tags.c.game_id == game_id,
            game_tags.c.tag_id == tag_id,
        )
    ).first()

    if exists:
        return True

    session.execute(
        insert(game_tags).values(game_id=game_id, tag_id=tag_id)
    )
    session.commit()
    return True


def detach_tag(session: Session, game_id: int, tag_id: int) -> bool:
    session.execute(
        delete(game_tags).where(
            game_tags.c.game_id == game_id,
            game_tags.c.tag_id == tag_id,
        )
    )
    session.commit()
    return True


def list_tags_for_game(session: Session, game_id: int) -> list[Tag]:
    return (
        session.query(Tag)
        .join(game_tags, Tag.id == game_tags.c.tag_id)
        .filter(game_tags.c.game_id == game_id)
        .order_by(Tag.name)
        .all()
    )
