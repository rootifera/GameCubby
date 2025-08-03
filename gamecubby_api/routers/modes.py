from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.mode import Mode as ModeSchema
from ..utils.mode import list_modes, sync_modes, get_mode_by_id
from ..utils.auth import get_current_admin

router = APIRouter(prefix="/modes", tags=["Modes"])


@router.get("/", response_model=list[ModeSchema])
def get_all_modes(db: Session = Depends(get_db)):
    return list_modes(db)


@router.get("/{mode_id}", response_model=ModeSchema)
def get_mode(mode_id: int, db: Session = Depends(get_db)):
    mode = get_mode_by_id(db, mode_id)
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")
    return mode


@router.post("/sync", dependencies=[Depends(get_current_admin)])
async def sync_modes_endpoint(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    async def run_sync():
        await sync_modes(db)

    background_tasks.add_task(run_sync)
    return {"message": "Mode sync started in background."}
