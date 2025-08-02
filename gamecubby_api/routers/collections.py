from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.collection import Collection as CollectionSchema, CollectionCreate
from ..utils.collection import create_collection, get_collection, list_collections
from ..models.collection import Collection
from ..utils.auth import get_current_admin
from ..utils.external import fetch_igdb_collection

router = APIRouter(prefix="/collections", tags=["Collections"])


@router.post("/", response_model=CollectionSchema, dependencies=[Depends(get_current_admin)])
def add_collection(data: CollectionCreate, db: Session = Depends(get_db)):
    if db.query(Collection).filter_by(name=data.name).first():
        raise HTTPException(status_code=409, detail="Collection already exists")
    collection = create_collection(db, data.dict())
    return collection


@router.get("/", response_model=list[CollectionSchema])
def get_all_collections(db: Session = Depends(get_db)):
    collections = list_collections(db)
    return collections


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