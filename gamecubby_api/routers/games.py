from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone
from pathlib import Path
import json
import logging
import os
from ..db import get_db
from ..schemas.game import (
    Game as GameSchema,
    GameCreate,
    GameUpdate,
    AssignLocationRequest,
    AddGameFromIGDBRequest, GameCreateResponse, GamePreview,
)
from ..utils.game import (
    get_game,
    create_game,
    update_game,
    delete_game,
    add_game_from_igdb,
    convert_igdb_game_to_custom,
    check_game_metadata_status,
    refresh_game_metadata,
    refresh_all_games_metadata,
    force_refresh_metadata, list_games_preview, create_game_and_resolve_wishlist,
    add_igdb_game_and_resolve_wishlist,
)
from ..utils.wishlist import (
    WishlistAlreadyResolvedError,
    WishlistNotFoundError,
    active_wishlist_ids_for_igdb,
)
from ..utils.game_tag import attach_tag, detach_tag, list_tags_for_game
from ..utils.game_platform import attach_platform, detach_platform, list_platforms_for_game
from ..schemas.tag import Tag as TagSchema
from ..schemas.platform import Platform as PlatformSchema
from ..utils.location import get_location_path
from ..utils.auth import get_current_admin
from ..utils.db_tools import with_db
from ..utils.job_lock import try_job_lock

router = APIRouter(prefix="/games", tags=["Games"])
logger = logging.getLogger(__name__)

METADATA_REFRESH_STATUS_FILE = Path(os.getenv("METADATA_REFRESH_STATUS_FILE", "storage/metadata_refresh_status.json"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_metadata_refresh_status() -> dict:
    try:
        if METADATA_REFRESH_STATUS_FILE.is_file():
            return json.loads(METADATA_REFRESH_STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to read metadata refresh status from %s", METADATA_REFRESH_STATUS_FILE)
    return {
        "status": "idle",
        "kind": None,
        "detail": "No metadata refresh has run yet.",
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }


def _write_metadata_refresh_status(payload: dict) -> None:
    METADATA_REFRESH_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = METADATA_REFRESH_STATUS_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(METADATA_REFRESH_STATUS_FILE)


def _start_metadata_refresh(background_tasks: BackgroundTasks, kind: str) -> dict:
    if kind == "force_refresh":
        detail = "Force refresh is running for all IGDB-linked games."
    else:
        detail = "Refreshing outdated metadata for all IGDB-linked games."

    started = {
        "status": "running",
        "kind": kind,
        "detail": detail,
        "started_at": _utc_now(),
        "finished_at": None,
        "result": None,
        "error": None,
    }
    _write_metadata_refresh_status(started)

    def do_refresh():
        with try_job_lock("metadata-refresh") as acquired:
            if not acquired:
                logger.info("Metadata refresh skipped; another API worker owns the job")
                return
            try:
                with with_db() as db:
                    if kind == "force_refresh":
                        result = force_refresh_metadata(db)
                    else:
                        result = refresh_all_games_metadata(db)
                _write_metadata_refresh_status({
                    "status": "completed",
                    "kind": kind,
                    "detail": "Metadata refresh completed.",
                    "started_at": started["started_at"],
                    "finished_at": _utc_now(),
                    "result": result,
                    "error": None,
                })
                logger.info("Metadata refresh completed. kind=%s result=%s", kind, result)
            except Exception as e:
                _write_metadata_refresh_status({
                    "status": "failed",
                    "kind": kind,
                    "detail": "Metadata refresh failed.",
                    "started_at": started["started_at"],
                    "finished_at": _utc_now(),
                    "result": None,
                    "error": str(e),
                })
                logger.exception("Metadata refresh failed. kind=%s", kind)

    background_tasks.add_task(do_refresh)
    return started


@router.get("/", response_model=List[GamePreview])
def get_all_games(db: Session = Depends(get_db)):
    return list_games_preview(db)


@router.get("/{game_id}", response_model=GameSchema)
def get_game_by_id(game_id: int, db: Session = Depends(get_db)):
    game = get_game(db, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    return game


@router.put("/{game_id}", response_model=GameSchema, dependencies=[Depends(get_current_admin)])
def edit_game(game_id: int, game: GameUpdate, db: Session = Depends(get_db)):
    try:
        updated = update_game(db, game_id, game.model_dump())
        if not updated:
            raise HTTPException(404, "Game not found")
        return updated
    except ValueError as e:
        raise HTTPException(403, str(e))


@router.delete("/{game_id}", response_model=bool, dependencies=[Depends(get_current_admin)])
def remove_game(game_id: int, db: Session = Depends(get_db)):
    deleted = delete_game(db, game_id)
    if not deleted:
        raise HTTPException(404, "Game not found")
    return True


@router.post("/from_igdb", response_model=GameCreateResponse, dependencies=[Depends(get_current_admin)])
async def add_game_from_igdb_endpoint(req: AddGameFromIGDBRequest, db: Session = Depends(get_db)):
    try:
        if req.wishlist_id:
            game = await add_igdb_game_and_resolve_wishlist(
                db,
                wishlist_id=req.wishlist_id,
                igdb_id=req.igdb_id,
                platform_ids=req.platform_ids,
                location_id=req.location_id,
                tag_ids=req.tag_ids,
                condition=req.condition,
                order=req.order,
            )
        else:
            game = await add_game_from_igdb(
                db,
                igdb_id=req.igdb_id,
                platform_ids=req.platform_ids,
                location_id=req.location_id,
                tag_ids=req.tag_ids,
                condition=req.condition,
                order=req.order,
            )
    except WishlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WishlistAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not game:
        raise HTTPException(404, "Game not found on IGDB")
    game.matching_wishlist_ids = [] if req.wishlist_id else active_wishlist_ids_for_igdb(db, req.igdb_id)
    return game


@router.get("/{game_id}/location_path", response_model=dict)
def get_game_location_path(game_id: int, db: Session = Depends(get_db)):
    path = get_location_path(db, game_id)
    if not path:
        raise HTTPException(404, "Game has no location assigned")
    return {"location_path": path}


@router.post("/", response_model=GameCreateResponse, dependencies=[Depends(get_current_admin)])
def add_game(game: GameCreate, db: Session = Depends(get_db)):
    data = game.model_dump()
    wishlist_id = data.pop("wishlist_id", None)
    try:
        created = (
            create_game_and_resolve_wishlist(db, data, wishlist_id)
            if wishlist_id else create_game(db, data)
        )
    except WishlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WishlistAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    created.matching_wishlist_ids = []
    return created


@router.get("/{game_id}/metadata-update-status")
async def game_metadata_update_status(game_id: int, db: Session = Depends(get_db)):
    status = await check_game_metadata_status(db, game_id)
    if status is None:
        raise HTTPException(404, "Game not found")
    return status


@router.post("/{game_id}/refresh_metadata", dependencies=[Depends(get_current_admin)])
async def refresh_metadata_endpoint(game_id: int, db: Session = Depends(get_db)):
    game, updated, msg = await refresh_game_metadata(db, game_id)
    if not game:
        raise HTTPException(404, msg)
    return {"game_id": game_id, "updated": updated, "message": msg}


@router.post("/{game_id}/convert_to_custom", response_model=GameSchema, dependencies=[Depends(get_current_admin)])
def convert_to_custom_endpoint(game_id: int, db: Session = Depends(get_db)):
    game = convert_igdb_game_to_custom(db, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    return game


@router.post("/refresh_all_metadata", dependencies=[Depends(get_current_admin)])
async def refresh_all_metadata_endpoint(background_tasks: BackgroundTasks):
    return _start_metadata_refresh(background_tasks, "refresh_all")


@router.get("/refresh_all_metadata/status", dependencies=[Depends(get_current_admin)])
async def refresh_all_metadata_status_endpoint():
    return _read_metadata_refresh_status()


@router.post("/force_refresh_metadata", dependencies=[Depends(get_current_admin)])
async def force_refresh_metadata_endpoint(background_tasks: BackgroundTasks):
    return _start_metadata_refresh(background_tasks, "force_refresh")
