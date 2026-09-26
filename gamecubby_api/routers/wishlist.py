from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from typing import Annotated

from ..db import get_db
from ..schemas.game import Game as GameSchema
from ..schemas.wishlist import (
    WishlistCreate,
    WishlistFromIGDBRequest,
    WishlistItem as WishlistItemSchema,
    WishlistPurchaseRequest,
    WishlistResolveRequest,
    WishlistUpdate,
)
from ..utils.auth import get_current_admin
from ..utils.external import fetch_igdb_game
from ..utils.formatting import format_igdb_game
from ..utils.game import purchase_wishlist_item
from ..utils.platform import upsert_platform
from ..utils.wishlist import (
    create_wishlist_item,
    delete_wishlist_item,
    get_wishlist_item,
    list_wishlist_items,
    resolve_wishlist_item,
    update_wishlist_item,
    WishlistAlreadyResolvedError,
    WishlistNotFoundError,
)


router = APIRouter(prefix="/wishlist", tags=["Wishlist"])


@router.get("/", response_model=list[WishlistItemSchema])
def list_items(status: str | None = None, include_resolved: bool = False, db: Session = Depends(get_db)):
    try:
        return list_wishlist_items(db, status=status, include_resolved=include_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{wishlist_id}", response_model=WishlistItemSchema)
def get_item(wishlist_id: int, db: Session = Depends(get_db)):
    item = get_wishlist_item(db, wishlist_id)
    if not item:
        raise HTTPException(status_code=404, detail="Wishlist item not found")
    return item


@router.post("/", response_model=WishlistItemSchema, dependencies=[Depends(get_current_admin)])
def create_item(payload: WishlistCreate, db: Session = Depends(get_db)):
    try:
        return create_wishlist_item(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/{wishlist_id}", response_model=WishlistItemSchema, dependencies=[Depends(get_current_admin)])
def edit_item(wishlist_id: int, payload: WishlistUpdate, db: Session = Depends(get_db)):
    try:
        item = update_wishlist_item(db, wishlist_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not item:
        raise HTTPException(status_code=404, detail="Wishlist item not found")
    return item


@router.delete("/{wishlist_id}", status_code=204, dependencies=[Depends(get_current_admin)])
def remove_item(wishlist_id: int, db: Session = Depends(get_db)):
    if not delete_wishlist_item(db, wishlist_id):
        raise HTTPException(status_code=404, detail="Wishlist item not found")


@router.post("/from_igdb", response_model=WishlistItemSchema, dependencies=[Depends(get_current_admin)])
async def add_item_from_igdb(payload: WishlistFromIGDBRequest, db: Session = Depends(get_db)):
    raw = await fetch_igdb_game(payload.igdb_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Game not found on IGDB")

    game = format_igdb_game(raw, db)
    available_platforms = {platform["id"]: platform for platform in game["platforms"]}
    selected_ids = payload.platform_ids or list(available_platforms)
    invalid_ids = sorted(set(selected_ids) - set(available_platforms))
    if invalid_ids:
        raise HTTPException(status_code=422, detail=f"Platforms are not available for this IGDB game: {invalid_ids}")
    for platform_id in selected_ids:
        upsert_platform(db, available_platforms[platform_id])

    try:
        return create_wishlist_item(db, {
            "igdb_id": payload.igdb_id,
            "name": game["name"],
            "release_year": game["release_date"],
            "cover_url": game["cover_url"],
            "platform_ids": selected_ids,
            "links": [link.model_dump() for link in payload.links],
        })
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/{wishlist_id}/purchase", response_model=GameSchema, dependencies=[Depends(get_current_admin)])
async def purchase_item(wishlist_id: Annotated[int, Path(gt=0)], payload: WishlistPurchaseRequest, db: Session = Depends(get_db)):
    try:
        return await purchase_wishlist_item(
            db,
            wishlist_id=wishlist_id,
            location_id=payload.location_id,
            condition=payload.condition,
            order=payload.order,
            tag_ids=payload.tag_ids,
        )
    except WishlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WishlistAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{wishlist_id}/resolve", response_model=WishlistItemSchema, dependencies=[Depends(get_current_admin)])
def resolve_item(wishlist_id: Annotated[int, Path(gt=0)], payload: WishlistResolveRequest, db: Session = Depends(get_db)):
    try:
        return resolve_wishlist_item(db, wishlist_id, payload.game_id)
    except WishlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WishlistAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
