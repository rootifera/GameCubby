from typing import Optional

from sqlalchemy.orm import Session, selectinload

from ..models.platform import Platform
from ..models.game import Game
from ..models.wishlist import WishlistItem, WishlistLink


class WishlistNotFoundError(ValueError):
    pass


class WishlistAlreadyResolvedError(ValueError):
    pass


def _with_relations(query):
    return query.options(selectinload(WishlistItem.platforms), selectinload(WishlistItem.links))


def list_wishlist_items(
    db: Session, *, status: str | None = None, include_resolved: bool = False
) -> list[WishlistItem]:
    query = _with_relations(db.query(WishlistItem))
    if status is not None:
        if status not in {"active", "in_library"}:
            raise ValueError("status must be 'active' or 'in_library'")
        query = query.filter(WishlistItem.status == status)
    elif not include_resolved:
        query = query.filter(WishlistItem.status == "active")
    return query.order_by(WishlistItem.name).all()


def get_wishlist_item(db: Session, wishlist_id: int) -> Optional[WishlistItem]:
    return _with_relations(db.query(WishlistItem)).filter(WishlistItem.id == wishlist_id).first()


def active_wishlist_ids_for_igdb(db: Session, igdb_id: int) -> list[int]:
    return [
        row[0]
        for row in (
            db.query(WishlistItem.id)
            .filter(WishlistItem.status == "active", WishlistItem.igdb_id == igdb_id)
            .order_by(WishlistItem.id)
            .all()
        )
    ]


def resolve_wishlist_item(
    db: Session, wishlist_id: int, game_id: int, *, commit: bool = True
) -> WishlistItem:
    item = (
        _with_relations(db.query(WishlistItem))
        .filter(WishlistItem.id == wishlist_id)
        .with_for_update()
        .first()
    )
    if not item:
        raise WishlistNotFoundError("Wishlist item not found")
    if item.status != "active":
        raise WishlistAlreadyResolvedError("Wishlist item is already resolved")
    if not db.get(Game, game_id):
        raise ValueError("Library game not found")

    item.status = "in_library"
    item.library_game_id = game_id
    if commit:
        db.commit()
        return get_wishlist_item(db, wishlist_id)
    db.flush()
    return item


def active_wishlist_item_for_update(db: Session, wishlist_id: int) -> WishlistItem:
    item = (
        _with_relations(db.query(WishlistItem))
        .filter(WishlistItem.id == wishlist_id)
        .with_for_update()
        .first()
    )
    if not item:
        raise WishlistNotFoundError("Wishlist item not found")
    if item.status != "active":
        raise WishlistAlreadyResolvedError("Wishlist item is already resolved")
    return item


def _platforms_for_ids(db: Session, platform_ids: list[int]) -> list[Platform]:
    ids = list(dict.fromkeys(platform_ids))
    if not ids:
        return []
    platforms = db.query(Platform).filter(Platform.id.in_(ids)).all()
    if len(platforms) != len(ids):
        found = {platform.id for platform in platforms}
        missing = sorted(set(ids) - found)
        raise ValueError(f"Unknown platform IDs: {missing}")
    by_id = {platform.id: platform for platform in platforms}
    return [by_id[platform_id] for platform_id in ids]


def _replace_links(item: WishlistItem, links: list[dict]) -> None:
    item.links = [WishlistLink(label=link["label"].strip(), url=link["url"].strip()) for link in links]


def create_wishlist_item(db: Session, payload: dict) -> WishlistItem:
    platform_ids = payload.pop("platform_ids", [])
    links = payload.pop("links", [])
    item = WishlistItem(**payload)
    item.platforms = _platforms_for_ids(db, platform_ids)
    _replace_links(item, links)
    db.add(item)
    db.commit()
    return get_wishlist_item(db, item.id)


def update_wishlist_item(db: Session, wishlist_id: int, payload: dict) -> Optional[WishlistItem]:
    item = get_wishlist_item(db, wishlist_id)
    if not item:
        return None

    if "platform_ids" in payload:
        item.platforms = _platforms_for_ids(db, payload.pop("platform_ids"))
    if "links" in payload:
        _replace_links(item, payload.pop("links"))
    for key, value in payload.items():
        setattr(item, key, value)

    db.commit()
    return get_wishlist_item(db, item.id)


def delete_wishlist_item(db: Session, wishlist_id: int) -> bool:
    item = db.get(WishlistItem, wishlist_id)
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True
