from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.game import (
    Game as GameSchema,
    GameCreate,
    GameUpdate,
    AssignLocationRequest, AddGameFromIGDBRequest,
)
from ..utils.game import (
    list_games,
    get_game,
    create_game,
    update_game,
    delete_game,
    list_games_by_tag,
    list_games_by_platform,
    list_games_by_location, add_game_from_igdb,
)
from ..utils.game_tag import attach_tag, detach_tag, list_tags_for_game
from ..utils.game_platform import attach_platform, detach_platform, list_platforms_for_game
from ..schemas.tag import Tag as TagSchema
from ..schemas.platform import Platform as PlatformSchema
from ..utils.location import get_location_path

router = APIRouter(prefix="/games", tags=["Games"])

@router.get("/", response_model=list[GameSchema])
def get_all_games(db: Session = Depends(get_db)):
    return list_games(db)

@router.get("/{game_id}", response_model=GameSchema)
def get_game_by_id(game_id: int, db: Session = Depends(get_db)):
    game = get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game

@router.put("/{game_id}", response_model=GameSchema)
def edit_game(game_id: int, game: GameUpdate, db: Session = Depends(get_db)):
    updated = update_game(db, game_id, game.dict())
    if not updated:
        raise HTTPException(status_code=404, detail="Game not found")
    return updated


@router.delete("/{game_id}", response_model=bool)
def remove_game(game_id: int, db: Session = Depends(get_db)):
    deleted = delete_game(db, game_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Game not found")
    return True


@router.post("/{game_id}/tags/{tag_id}", response_model=bool)
def add_tag_to_game(game_id: int, tag_id: int, db: Session = Depends(get_db)):
    ok = attach_tag(db, game_id, tag_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Game or Tag not found")
    return True

@router.delete("/{game_id}/tags/{tag_id}", response_model=bool)
def remove_tag_from_game(game_id: int, tag_id: int, db: Session = Depends(get_db)):
    detach_tag(db, game_id, tag_id)
    return True

@router.get("/{game_id}/tags", response_model=list[TagSchema])
def get_tags_for_game(game_id: int, db: Session = Depends(get_db)):
    return list_tags_for_game(db, game_id)

@router.post("/{game_id}/platforms/{platform_id}", response_model=bool)
def add_platform_to_game(game_id: int, platform_id: int, db: Session = Depends(get_db)):
    ok = attach_platform(db, game_id, platform_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Game or Platform not found")
    return True

@router.delete("/{game_id}/platforms/{platform_id}", response_model=bool)
def remove_platform_from_game(game_id: int, platform_id: int, db: Session = Depends(get_db)):
    detach_platform(db, game_id, platform_id)
    return True

@router.get("/{game_id}/platforms", response_model=list[PlatformSchema])
def get_platforms_for_game(game_id: int, db: Session = Depends(get_db)):
    return list_platforms_for_game(db, game_id)

@router.post("/{game_id}/assign_location", response_model=GameSchema)
def assign_location(game_id: int, req: AssignLocationRequest, db: Session = Depends(get_db)):
    updated = update_game(db, game_id, {"location_id": req.location_id, "order": req.order})
    if not updated:
        raise HTTPException(status_code=404, detail="Game not found")
    return updated


@router.post("/from_igdb", response_model=GameSchema)
async def add_game_from_igdb_endpoint(
    req: AddGameFromIGDBRequest, db: Session = Depends(get_db)
):
    game = await add_game_from_igdb(
        db,
        igdb_id=req.igdb_id,
        platform_ids=req.platform_ids,
        location_id=req.location_id,
        tag_ids=req.tag_ids,
        condition=req.condition,
        order=req.order,
    )
    if not game:
        raise HTTPException(status_code=404, detail="Game not found on IGDB")
    return game

@router.get("/game/{game_id}/location_path")
async def get_game_location_path(game_id: int, db: Session = Depends(get_db)):
    path = get_location_path(db, game_id)
    if not path:
        raise HTTPException(status_code=404, detail="Location path not found")
    return {"location_path": path}

@router.post("/", response_model=GameSchema)
def add_game(game: GameCreate, db: Session = Depends(get_db)):
    game_obj = create_game(db, game.dict())
    return game_obj