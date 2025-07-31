from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..utils.playerperspective import sync_player_perspectives, get_player_perspective_by_id
from ..models.playerperspective import PlayerPerspective
from ..utils.auth import get_current_admin

router = APIRouter(prefix="/perspectives", tags=["Player Perspectives"])


@router.post("/sync", dependencies=[Depends(get_current_admin)])
async def sync_perspectives(db: Session = Depends(get_db)):
    try:
        count = await sync_player_perspectives(db)
        return {"message": "Player perspectives synced successfully.", "synced": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=list[dict])
def list_perspectives(db: Session = Depends(get_db)):
    perspectives = db.query(PlayerPerspective).order_by(PlayerPerspective.name).all()
    return [{"id": p.id, "name": p.name} for p in perspectives]


@router.get("/{perspective_id}", response_model=dict)
def get_perspective_by_id(perspective_id: int, db: Session = Depends(get_db)):
    perspective = get_player_perspective_by_id(db, perspective_id)
    if not perspective:
        raise HTTPException(status_code=404, detail="Player perspective not found")
    return {"id": perspective.id, "name": perspective.name}
