from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.platform import Platform as PlatformSchema
from ..utils.platform import get_platform, list_platforms

router = APIRouter(prefix="/platforms", tags=["Platforms"])

@router.get("/", response_model=list[PlatformSchema])
def get_all_platforms(db: Session = Depends(get_db)):
    return list_platforms(db)

@router.get("/{platform_id}", response_model=PlatformSchema)
def get_platform_by_id(platform_id: int, db: Session = Depends(get_db)):
    platform = get_platform(db, platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")
    return platform
