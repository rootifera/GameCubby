from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from ..schemas.app_config import AppConfigEntry
from ..utils.auth import get_current_admin
from ..utils.app_config import (
    get_app_config_value,
    set_app_config_value,
    delete_app_config_key,
    list_all_app_config,
)

router = APIRouter(prefix="/app_config", tags=["App Config"])


@router.get("/", response_model=List[AppConfigEntry], dependencies=[Depends(get_current_admin)])
def get_all_configs(db: Session = Depends(get_db)):
    return list_all_app_config(db)


@router.get("/{key}", response_model=AppConfigEntry, dependencies=[Depends(get_current_admin)])
def get_config_by_key(key: str, db: Session = Depends(get_db)):
    value = get_app_config_value(db, key)
    if value is None:
        raise HTTPException(status_code=404, detail="Config key not found")
    return AppConfigEntry(key=key, value=value)


@router.post("/", response_model=AppConfigEntry, dependencies=[Depends(get_current_admin)])
def set_config(entry: AppConfigEntry, db: Session = Depends(get_db)):
    return set_app_config_value(db, entry.key, entry.value)


@router.delete("/{key}", response_model=bool, dependencies=[Depends(get_current_admin)])
def delete_config(key: str, db: Session = Depends(get_db)):
    ok = delete_app_config_key(db, key)
    if not ok:
        raise HTTPException(status_code=404, detail="Config key not found")
    return True
