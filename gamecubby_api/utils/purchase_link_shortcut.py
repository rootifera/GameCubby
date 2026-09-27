from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.purchase_link_shortcut import PurchaseLinkShortcut


class DuplicatePurchaseLinkShortcutError(ValueError):
    pass


def _normalise_label(label: str) -> str:
    value = label.strip()
    if not value:
        raise ValueError("Label must not be blank")
    if len(value) > 100:
        raise ValueError("Label must be at most 100 characters")
    return value


def _label_exists(db: Session, label: str, *, excluding_id: int | None = None) -> bool:
    query = db.query(PurchaseLinkShortcut.id).filter(
        func.lower(func.trim(PurchaseLinkShortcut.label)) == label.casefold()
    )
    if excluding_id is not None:
        query = query.filter(PurchaseLinkShortcut.id != excluding_id)
    return query.first() is not None


def list_purchase_link_shortcuts(db: Session) -> list[PurchaseLinkShortcut]:
    return db.query(PurchaseLinkShortcut).order_by(
        PurchaseLinkShortcut.sort_order.asc(),
        func.lower(PurchaseLinkShortcut.label).asc(),
    ).all()


def create_purchase_link_shortcut(db: Session, label: str, sort_order: int = 0) -> PurchaseLinkShortcut:
    label = _normalise_label(label)
    if _label_exists(db, label):
        raise DuplicatePurchaseLinkShortcutError("A shortcut with this label already exists")
    shortcut = PurchaseLinkShortcut(label=label, sort_order=sort_order)
    db.add(shortcut)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicatePurchaseLinkShortcutError("A shortcut with this label already exists") from exc
    db.refresh(shortcut)
    return shortcut


def update_purchase_link_shortcut(
    db: Session, shortcut_id: int, *, label: str | None = None, sort_order: int | None = None
) -> PurchaseLinkShortcut | None:
    shortcut = db.get(PurchaseLinkShortcut, shortcut_id)
    if not shortcut:
        return None
    if label is not None:
        label = _normalise_label(label)
        if _label_exists(db, label, excluding_id=shortcut_id):
            raise DuplicatePurchaseLinkShortcutError("A shortcut with this label already exists")
        shortcut.label = label
    if sort_order is not None:
        shortcut.sort_order = sort_order
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicatePurchaseLinkShortcutError("A shortcut with this label already exists") from exc
    db.refresh(shortcut)
    return shortcut


def delete_purchase_link_shortcut(db: Session, shortcut_id: int) -> bool:
    shortcut = db.get(PurchaseLinkShortcut, shortcut_id)
    if not shortcut:
        return False
    db.delete(shortcut)
    db.commit()
    return True


def reorder_purchase_link_shortcuts(db: Session, items: list[dict]) -> list[PurchaseLinkShortcut]:
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Each shortcut ID may appear only once")
    shortcuts = db.query(PurchaseLinkShortcut).filter(PurchaseLinkShortcut.id.in_(ids)).all()
    by_id = {shortcut.id: shortcut for shortcut in shortcuts}
    missing = sorted(set(ids) - set(by_id))
    if missing:
        raise LookupError(f"Purchase link shortcuts not found: {missing}")
    try:
        for item in items:
            by_id[item["id"]].sort_order = item["sort_order"]
        db.commit()
    except Exception:
        db.rollback()
        raise
    return list_purchase_link_shortcuts(db)
