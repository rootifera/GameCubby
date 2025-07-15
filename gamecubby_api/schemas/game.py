from pydantic import BaseModel

class AssignLocationRequest(BaseModel):
    location_id: int
    order: int | None = None

class Game(BaseModel):
    id: int
    igdb_id: int | None = None
    name: str
    summary: str | None = None
    release_date: str | None = None
    cover_url: str | None = None
    played: bool | None = None
    condition: int | None = None
    location_id: int | None = None
    order: int | None = None

    class Config:
        from_attributes = True


class GameCreate(BaseModel):
    igdb_id: int | None = None
    name: str
    summary: str | None = None
    release_date: str | None = None
    cover_url: str | None = None
    condition: int | None = None
    location_id: int | None = None
    order: int | None = None

class GameUpdate(BaseModel):
    name: str | None = None
    igdb_id: int | None = None
    summary: str | None = None
    release_date: str | None = None
    cover_url: str | None = None
    condition: int | None = None
    location_id: int | None = None
    order: int | None = None