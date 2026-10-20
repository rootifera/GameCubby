from fastapi import APIRouter, Depends, HTTPException, Response, Body
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.game import GameIdName
from ..schemas.location import (
    Location as LocationSchema, LocationMigrationResult, LocationMigrationRequest,
    FillOrderGapsRequest, FillOrderGapsResponse, OrderReport,
)
from ..utils.game import list_games_by_location
from ..utils.location import (
    create_location,
    get_location,
    list_top_locations,
    list_child_locations,
    list_all_locations,
    delete_location, rename_location, migrate_location_games,
    plan_order_renumbering, apply_order_renumbering, StaleOrderPlanError, report_order_problems,
)
from ..utils.auth import get_current_admin

router = APIRouter(prefix="/locations", tags=["Locations"])


@router.post("/", response_model=LocationSchema, dependencies=[Depends(get_current_admin)])
def add_location(
        name: str,
        parent_id: int = None,
        type: str = None,
        db: Session = Depends(get_db),
):
    location = create_location(db, name, parent_id, type)
    return location


@router.get("/top", response_model=list[LocationSchema])
def get_top_locations(db: Session = Depends(get_db)):
    return list_top_locations(db)


@router.get("/children/{parent_id}", response_model=list[LocationSchema])
def get_children(parent_id: int, db: Session = Depends(get_db)):
    return list_child_locations(db, parent_id)


@router.get("/", response_model=list[LocationSchema])
def get_all_locations(db: Session = Depends(get_db)):
    return list_all_locations(db)


@router.get("/order-report", response_model=OrderReport, dependencies=[Depends(get_current_admin)])
def order_report(db: Session = Depends(get_db)):
    """
    Read-only report on the numbering of ALL locations: gaps (with the games either side of each),
    duplicate numbers, and locations whose first game isn't #1. Nothing is changed.
    (Declared before /{location_id} so "order-report" isn't parsed as a location id.)
    """
    return report_order_problems(db)


@router.get("/{location_id}", response_model=LocationSchema)
def get_single_location(location_id: int, db: Session = Depends(get_db)):
    location = get_location(db, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.delete("/{location_id}", status_code=204, dependencies=[Depends(get_current_admin)])
def remove_location(location_id: int, db: Session = Depends(get_db)):
    location = get_location(db, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    ok = delete_location(db, location_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Location cannot be deleted: it has child locations or games assigned."
        )

    return Response(status_code=204)


@router.put("/{location_id}/rename", response_model=LocationSchema, dependencies=[Depends(get_current_admin)])
def rename_location_endpoint(
        location_id: int,
        name: str = Body(..., embed=True),
        db: Session = Depends(get_db),
):
    loc = get_location(db, location_id)
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    try:
        updated = rename_location(db, location_id, name)
        if not updated:
            raise HTTPException(status_code=404, detail="Location not found")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/migrate",
    response_model=LocationMigrationResult,
    dependencies=[Depends(get_current_admin)],
)
def migrate_location_endpoint(
        payload: LocationMigrationRequest,
        db: Session = Depends(get_db),
):
    """
    Bulk-migrate all games from source_location_id to target_location_id.
    - Validates target exists.
    - Lenient on source: if it doesn't exist or has no games, result is migrated=0.
    """
    try:
        migrated_count = migrate_location_games(
            db,
            source_location_id=payload.source_location_id,
            target_location_id=payload.target_location_id,
        )
        return LocationMigrationResult(migrated=int(migrated_count))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{location_id}/games", response_model=list[GameIdName])
def list_games_for_location(location_id: int, db: Session = Depends(get_db)):
    """
    Return only id and name for games assigned to the specified location.
    """
    if not get_location(db, location_id):
        raise HTTPException(status_code=404, detail="Location not found")

    games = list_games_by_location(db, location_id)
    return [GameIdName(id=g.id, name=g.name) for g in games]


@router.post(
    "/{location_id}/fill-order-gaps",
    response_model=FillOrderGapsResponse,
    dependencies=[Depends(get_current_admin)],
)
def fill_order_gaps(location_id: int, payload: FillOrderGapsRequest, db: Session = Depends(get_db)):
    """
    Renumber the games of a location (optionally with all its sub-locations) so their order numbers
    run 1..N with no gaps or duplicates. Each location is numbered on its own.

    Two steps, on purpose: call with `apply=false` to PREVIEW (nothing is written), then with
    `apply=true` and the preview's `fingerprint` to write exactly what was previewed.
    """
    if not get_location(db, location_id):
        raise HTTPException(status_code=404, detail="Location not found")
    if not payload.apply:
        return plan_order_renumbering(db, location_id, payload.include_children)
    if not payload.fingerprint:
        raise HTTPException(status_code=400, detail="Preview first: applying needs the fingerprint from the preview.")
    try:
        return apply_order_renumbering(db, location_id, payload.include_children, payload.fingerprint)
    except StaleOrderPlanError as e:
        raise HTTPException(status_code=409, detail=str(e))
