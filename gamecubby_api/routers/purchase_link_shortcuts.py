from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas.purchase_link_shortcut import (
    PurchaseLinkShortcut as PurchaseLinkShortcutSchema,
    PurchaseLinkShortcutCreate,
    PurchaseLinkShortcutReorderRequest,
    PurchaseLinkShortcutUpdate,
)
from ..utils.auth import get_current_admin
from ..utils.purchase_link_shortcut import (
    DuplicatePurchaseLinkShortcutError,
    create_purchase_link_shortcut,
    delete_purchase_link_shortcut,
    list_purchase_link_shortcuts,
    reorder_purchase_link_shortcuts,
    update_purchase_link_shortcut,
)


router = APIRouter(
    prefix="/purchase-link-shortcuts",
    tags=["Purchase Link Shortcuts"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/", response_model=list[PurchaseLinkShortcutSchema])
def list_shortcuts(db: Session = Depends(get_db)):
    return list_purchase_link_shortcuts(db)


@router.post("/", response_model=PurchaseLinkShortcutSchema, status_code=201)
def create_shortcut(payload: PurchaseLinkShortcutCreate, db: Session = Depends(get_db)):
    try:
        return create_purchase_link_shortcut(db, payload.label, payload.sort_order)
    except DuplicatePurchaseLinkShortcutError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/reorder", response_model=list[PurchaseLinkShortcutSchema])
def reorder_shortcuts(payload: PurchaseLinkShortcutReorderRequest, db: Session = Depends(get_db)):
    try:
        return reorder_purchase_link_shortcuts(db, [item.model_dump() for item in payload.items])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/{shortcut_id}", response_model=PurchaseLinkShortcutSchema)
def update_shortcut(shortcut_id: int, payload: PurchaseLinkShortcutUpdate, db: Session = Depends(get_db)):
    if payload.label is None and payload.sort_order is None:
        raise HTTPException(status_code=422, detail="Provide label or sort_order")
    try:
        shortcut = update_purchase_link_shortcut(
            db, shortcut_id, label=payload.label, sort_order=payload.sort_order
        )
    except DuplicatePurchaseLinkShortcutError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not shortcut:
        raise HTTPException(status_code=404, detail="Purchase link shortcut not found")
    return shortcut


@router.delete("/{shortcut_id}", status_code=204)
def delete_shortcut(shortcut_id: int, db: Session = Depends(get_db)):
    if not delete_purchase_link_shortcut(db, shortcut_id):
        raise HTTPException(status_code=404, detail="Purchase link shortcut not found")
