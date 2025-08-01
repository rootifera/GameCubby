from sqlalchemy.orm import Session
from fastapi import HTTPException
from ..models.tag import Tag


def upsert_tag(session: Session, tag_name: str) -> Tag:
    """
    Insert or fetch a tag by name (case-insensitive).
    Always stores tag names as lowercase.
    Returns the Tag object.
    """
    tag_name = tag_name.lower().strip()
    tag = session.query(Tag).filter_by(name=tag_name).first()
    if not tag:
        tag = Tag(name=tag_name)
        session.add(tag)
        session.commit()
        session.refresh(tag)
    return tag


def get_tag(session: Session, tag_id: int) -> Tag:
    """
    Retrieve a tag by ID or raise 404.
    """
    tag = session.query(Tag).filter_by(id=tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


def list_tags(session: Session) -> list[Tag]:
    """
    Return all tags, sorted by name.
    """
    return session.query(Tag).order_by(Tag.name).all()


def delete_tag(session: Session, tag_id: int) -> None:
    """
    Delete a tag by ID or raise 404.
    """
    tag = get_tag(session, tag_id)
    session.delete(tag)
    session.commit()
