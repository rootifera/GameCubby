from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.location import Location as LocationSchema
from ..utils.location import (
    create_location, get_location, list_top_locations, list_child_locations, list_all_locations
)
from ..utils.auth import get_current_admin

router = APIRouter(prefix="/locations", tags=["Locations"])


@router.post("/", response_model=LocationSchema, dependencies=[Depends(get_current_admin)])
def add_location(
        name: str,
        parent_id: int = None,
        type: str = None,
        db: Session = Depends(get_db)
):
    location = create_location(db, name, parent_id, type)
    return location


@router.get("/top", response_model=list[LocationSchema])
def get_top_locations(db: Session = Depends(get_db)):
    return list_top_locations(db)


@router.get("/children/{parent_id}", response_model=list[LocationSchema])
def get_children(parent_id: int, db: Session = Depends(get_db)):
    return list_child_locations(db, parent_id)


@router.get("/", response_model=list[LocationSchema])
def get_all_locations(db: Session = Depends(get_db)):
    return list_all_locations(db)


@router.get("/{location_id}", response_model=LocationSchema)
def get_single_location(location_id: int, db: Session = Depends(get_db)):
    location = get_location(db, location_id)
    if not location:
        raise HTTPException(404, "Location not found")
    return location
