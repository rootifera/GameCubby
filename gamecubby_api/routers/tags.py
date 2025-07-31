from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.tag import Tag as TagSchema
from ..utils.tag import upsert_tag, get_tag, list_tags, delete_tag
from ..utils.auth import get_current_admin
from ..utils.response import success_response, error_response

router = APIRouter(prefix="/tags", tags=["Tags"])


@router.post("/")
def create_tag(name: str, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    tag = upsert_tag(db, name)
    return success_response(data=tag)


@router.get("/", response_model=list[TagSchema])
def read_tags(db: Session = Depends(get_db)):
    tags = list_tags(db)
    return success_response(data={"tags": tags})


@router.get("/{tag_id}", response_model=TagSchema)
def read_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = get_tag(db, tag_id)
    if not tag:
        return error_response("Tag not found", 404)
    return success_response(data=tag)


@router.delete("/{tag_id}")
def remove_tag(tag_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    deleted = delete_tag(db, tag_id)
    if not deleted:
        return error_response("Tag not found", 404)
    return success_response(message="Tag deleted successfully.")
