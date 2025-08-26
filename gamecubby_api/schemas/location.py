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
