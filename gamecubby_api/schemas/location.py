from pydantic import BaseModel


class Location(BaseModel):
    id: int
    name: str
    parent_id: int | None = None
    type: str | None = None

    class Config:
        from_attributes = True


class LocationMigrationRequest(BaseModel):
    """
    Payload for migrating all games from one location to another.
    """
    source_location_id: int
    target_location_id: int


class LocationMigrationResult(BaseModel):
    """
    Response model for a migration operation.
    """
    migrated: int


class FillOrderGapsRequest(BaseModel):
    """
    Renumber the games in a location (optionally including all its sub-locations) so their order
    numbers run 1, 2, 3, ... with no gaps or duplicates. `apply=false` only previews.
    """
    include_children: bool = False
    apply: bool = False
    fingerprint: str | None = None  # from the preview; required when apply=true


class OrderChange(BaseModel):
    game_id: int
    name: str
    old: int
    new: int


class OrderTieGame(BaseModel):
    game_id: int
    name: str
    new: int


class OrderTie(BaseModel):
    order: int
    games: list[OrderTieGame]


class OrderLocationPlan(BaseModel):
    location_id: int
    path: list[str]
    games: int
    changed: int
    changes: list[OrderChange]
    ties: list[OrderTie]


class FillOrderGapsResponse(BaseModel):
    applied: bool
    fingerprint: str
    locations: list[OrderLocationPlan]
    total_games: int
    total_changed: int


class OrderGameRef(BaseModel):
    game_id: int
    name: str
    order: int


class OrderGap(BaseModel):
    """Numbers missing between two neighbouring games, e.g. #4 (and #5) missing between #3 and #6."""
    start: int
    end: int
    count: int
    after: OrderGameRef | None  # the game just before the gap
    before: OrderGameRef | None  # the game just after the gap


class OrderDuplicate(BaseModel):
    order: int
    games: list[OrderGameRef]


class OrderProblemLocation(BaseModel):
    location_id: int
    path: list[str]
    games: int
    starts_at: int | None  # set when the first game isn't #1
    gaps: list[OrderGap]
    duplicates: list[OrderDuplicate]
    fixable_changes: int  # how many games "Fill order gaps" would renumber here


class OrderReport(BaseModel):
    locations_checked: int  # locations that hold at least one numbered game
    games_checked: int
    locations_ok: int
    with_gaps: int
    with_duplicates: int
    not_starting_at_1: int
    problem_locations: list[OrderProblemLocation]
