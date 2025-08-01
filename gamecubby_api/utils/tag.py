from sqlalchemy.orm import Session
from ..models.tag import Tag


def upsert_tag(session: Session, tag_name: str):
    """
    Insert or fetch a tag by name (case-insensitive).
    Always stores tag names as lowercase.
    Returns the Tag object.
    """
    tag_name = tag_name.lower().strip()
    tag = session.query(Tag).filter(Tag.name == tag_name).first()
    if not tag:
        tag = Tag(name=tag_name)
        session.add(tag)
        session.commit()
        session.refresh(tag)
    return tag


def get_tag(session: Session, tag_id: int):
    """
    Retrieve a tag by ID.
    """
    return session.query(Tag).filter_by(id=tag_id).first()


def list_tags(session: Session):
    """
    Return all tags, sorted by name.
    """
    return session.query(Tag).order_by(Tag.name).all()


def delete_tag(session: Session, tag_id: int):
    """
    Delete a tag by ID.
    """
    tag = get_tag(session, tag_id)
    if tag:
        session.delete(tag)
        session.commit()
        return True
    return False
