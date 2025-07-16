from pydantic import BaseModel
from typing import Optional, List
from .platform import Platform
from .tag import Tag
from .collection import Collection

class AssignLocationRequest(BaseModel):
    location_id: int
    order: int | None = None

class Game(BaseModel):
    id: int
    igdb_id: int
    name: str
    summary: Optional[str]
    release_date: Optional[int]
    cover_url: Optional[str]
    condition: Optional[int]
    location_path: List[int] = []
    order: Optional[int]
    platforms: List[Platform] = []
    tags: List[Tag] = []
    collection: Optional[Collection] = None

    class Config:
        from_attributes = True


class GameCreate(BaseModel):
    igdb_id: int | None = None
    name: str
    summary: str | None = None
    release_date: int | None = None
    cover_url: str | None = None
    condition: int | None = None
    location_id: int | None = None
    order: int | None = None

class GameUpdate(BaseModel):
    name: str | None = None
    igdb_id: int | None = None
    summary: str | None = None
    release_date: int | None = None
    cover_url: str | None = None
    condition: int | None = None
    location_id: int | None = None
    order: int | None = None

class AddGameFromIGDBRequest(BaseModel):
    igdb_id: int
    platform_ids: list[int]
    location_id: int | None = None
    tag_ids: list[int] = []
    condition: int | None = None
    order: int | None = None