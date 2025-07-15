from sqlalchemy.orm import Session
from ..models.game_tag import game_tags
from ..models.game import Game
from ..models.tag import Tag

def attach_tag(session: Session, game_id: int, tag_id: int):
    game = session.query(Game).filter_by(id=game_id).first()
    tag = session.query(Tag).filter_by(id=tag_id).first()
    if not game or not tag:
        return False
    exists = session.execute(
        game_tags.select().where(
            game_tags.c.game_id == game_id,
            game_tags.c.tag_id == tag_id,
        )
    ).fetchone()
    if exists:
        return True
    session.execute(
        game_tags.insert().values(game_id=game_id, tag_id=tag_id)
    )
    session.commit()
    return True

def detach_tag(session: Session, game_id: int, tag_id: int):
    session.execute(
        game_tags.delete().where(
            game_tags.c.game_id == game_id,
            game_tags.c.tag_id == tag_id,
        )
    )
    session.commit()
    return True

def list_tags_for_game(session: Session, game_id: int):
    from ..schemas.tag import Tag as TagSchema
    result = (
        session.query(Tag)
        .join(game_tags, Tag.id == game_tags.c.tag_id)
        .filter(game_tags.c.game_id == game_id)
        .all()
    )
    return result
