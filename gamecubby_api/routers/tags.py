from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.tag import Tag as TagSchema
from ..utils.tag import upsert_tag, get_tag, list_tags, delete_tag
from ..utils.auth import get_current_admin

router = APIRouter(prefix="/tags", tags=["Tags"])


@router.post("/", response_model=TagSchema)
def create_tag(name: str, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    tag = upsert_tag(db, name)
    return tag


@router.get("/", response_model=list[TagSchema])
def read_tags(db: Session = Depends(get_db)):
    return list_tags(db)


@router.get("/{tag_id}", response_model=TagSchema)
def read_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = get_tag(db, tag_id)
    if not tag:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "detail": "Tag not found"}
        )
    return tag


@router.delete("/{tag_id}", response_model=bool)
def remove_tag(tag_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    deleted = delete_tag(db, tag_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tag not found")
    return True
