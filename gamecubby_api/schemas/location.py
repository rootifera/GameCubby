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
