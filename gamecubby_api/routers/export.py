from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..utils.auth import get_current_admin
from ..utils.export import (
    export_games_as_json,
    export_games_as_csv,
    export_games_as_excel,
)

router = APIRouter(prefix="/export", tags=["Export"])


@router.get("/games/json", dependencies=[Depends(get_current_admin)])
def export_games_json(db: Session = Depends(get_db)):
    return export_games_as_json(db)


@router.get("/games/csv", dependencies=[Depends(get_current_admin)])
def export_games_csv(db: Session = Depends(get_db)):
    return export_games_as_csv(db)


@router.get("/games/excel", dependencies=[Depends(get_current_admin)])
def export_games_excel(db: Session = Depends(get_db)):
    return export_games_as_excel(db)
