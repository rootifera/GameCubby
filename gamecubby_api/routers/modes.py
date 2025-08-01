from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.mode import Mode as ModeSchema
from ..utils.mode import (
    list_modes,
    assign_mode_to_game,
    remove_mode_from_game,
    sync_modes_from_igdb,
    get_mode_by_id,
)
from ..utils.auth import get_current_admin

router = APIRouter(prefix="/modes", tags=["Modes"])


@router.get("/", response_model=list[ModeSchema])
def get_all_modes(db: Session = Depends(get_db)):
    return list_modes(db)


@router.post("/assign", dependencies=[Depends(get_current_admin)])
def assign_mode(game_id: int, mode_id: int, db: Session = Depends(get_db)):
    ok = assign_mode_to_game(db, game_id, mode_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Game or Mode not found")
    return {"message": "Mode assigned to game."}


@router.post("/remove", dependencies=[Depends(get_current_admin)])
def remove_mode(game_id: int, mode_id: int, db: Session = Depends(get_db)):
    ok = remove_mode_from_game(db, game_id, mode_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Game or Mode not found")
    return {"message": "Mode removed from game."}


@router.post("/sync", dependencies=[Depends(get_current_admin)])
async def sync_modes_endpoint(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    async def run_sync():
        await sync_modes_from_igdb(db)

    background_tasks.add_task(run_sync)
    return {"message": "Mode sync started in background."}


@router.get("/{mode_id}", response_model=ModeSchema)
def get_mode(mode_id: int, db: Session = Depends(get_db)):
    mode = get_mode_by_id(db, mode_id)
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")
    return mode
