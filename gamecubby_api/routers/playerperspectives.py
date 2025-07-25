from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..utils.playerperspective import sync_player_perspectives
from ..models.playerperspective import PlayerPerspective

router = APIRouter(prefix="/perspectives", tags=["Player Perspectives"])


@router.post("/sync", response_model=dict)
async def sync_perspectives(db: Session = Depends(get_db)):
    try:
        count = await sync_player_perspectives(db)
        return {"status": "ok", "synced": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=list[dict])
def list_perspectives(db: Session = Depends(get_db)):
    perspectives = db.query(PlayerPerspective).order_by(PlayerPerspective.name).all()
    return [{"id": p.id, "name": p.name} for p in perspectives]
