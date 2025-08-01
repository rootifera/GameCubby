from sqlalchemy.orm import Session
from ..models.platform import Platform
from typing import Optional


def upsert_platform(session: Session, platform_data: dict) -> Platform:
    """
    Insert or update a platform in the DB.
    platform_data: dict with 'id', 'name', and (optional) 'slug'.
    Returns the Platform object.
    """
    platform = session.query(Platform).filter_by(id=platform_data["id"]).first()
    if platform:
        changed = False
        if platform.name != platform_data["name"]:
            platform.name = platform_data["name"]
            changed = True
        if platform.slug != platform_data.get("slug"):
            platform.slug = platform_data.get("slug")
            changed = True
        if changed:
            session.commit()
    else:
        platform = Platform(**platform_data)
        session.add(platform)
        session.commit()
    return platform


def get_platform(session: Session, platform_id: int) -> Optional[Platform]:
    return session.query(Platform).filter_by(id=platform_id).first()


def list_platforms(session: Session) -> list[Platform]:
    return session.query(Platform).order_by(Platform.name).all()


def ensure_platforms_exist(session: Session, platform_list: list[dict]) -> list[Platform]:
    """
    Given a list of platform dicts (from IGDB), upsert each platform
    and return a list of Platform ORM objects.
    """
    result = []
    for p in platform_list:
        result.append(upsert_platform(session, p))
    return result
