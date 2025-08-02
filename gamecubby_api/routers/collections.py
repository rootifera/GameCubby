from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.collection import Collection as CollectionSchema
from ..utils.collection import get_collection, list_collections
from ..utils.auth import get_current_admin
from ..utils.external import fetch_igdb_collection

router = APIRouter(prefix="/collections", tags=["Collections"])


@router.get("/", response_model=list[CollectionSchema])
def get_all_collections(db: Session = Depends(get_db)):
    return list_collections(db)


@router.get("/{collection_id}", response_model=CollectionSchema)
def get_collection_by_id(collection_id: int, db: Session = Depends(get_db)):
    collection = get_collection(db, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


@router.get("/collection_lookup/{game_id}", dependencies=[Depends(get_current_admin)])
async def collection_lookup(game_id: int):
    result = await fetch_igdb_collection(game_id)
    return {"collection": result}
