from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.mode import Mode as ModeSchema
from ..utils.mode import list_modes, assign_mode_to_game, remove_mode_from_game, sync_modes_from_igdb
from ..utils.auth import get_current_admin

router = APIRouter(prefix="/modes", tags=["Modes"])


@router.get("/", response_model=list[ModeSchema])
def get_all_modes(db: Session = Depends(get_db)):
    return list_modes(db)


@router.post("/assign", response_model=bool, dependencies=[Depends(get_current_admin)])
def assign_mode(game_id: int, mode_id: int, db: Session = Depends(get_db)):
    ok = assign_mode_to_game(db, game_id, mode_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Game or Mode not found")
    return True


@router.post("/remove", response_model=bool, dependencies=[Depends(get_current_admin)])
def remove_mode(game_id: int, mode_id: int, db: Session = Depends(get_db)):
    ok = remove_mode_from_game(db, game_id, mode_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Game or Mode not found")
    return True


@router.post("/sync", response_model=dict, dependencies=[Depends(get_current_admin)])
async def sync_modes_endpoint(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Fetches all modes from IGDB and updates the local table.
    Runs in the background.
    """

    async def run_sync():
        await sync_modes_from_igdb(db)

    background_tasks.add_task(run_sync)
    return {"status": "queued", "message": "Mode sync started in background"}
