from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from .platform import Platform
from .tag import Tag
from .collection import Collection
from .mode import Mode


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
    location_path: List[Dict[str, str]] = Field(default=[])
    order: Optional[int]
    platforms: List[Platform] = []
    tags: List[Tag] = []
    collection: Optional[Collection] = None
    modes: list[Mode] = []

    class Config:
        from_attributes = True


class GameCreate(BaseModel):
    igdb_id: Optional[int] = None
    name: str
    summary: Optional[str] = None
    release_date: Optional[int] = None
    cover_url: Optional[str] = None
    condition: Optional[int] = None
    location_id: Optional[int] = None
    order: Optional[int] = None
    mode_ids: Optional[List[int]] = []

    class Config:
        from_attributes = True


class GameUpdate(BaseModel):
    name: Optional[str] = None
    summary: Optional[str] = None
    release_date: Optional[int] = None
    cover_url: Optional[str] = None
    condition: Optional[int] = None
    location_id: Optional[int] = None
    order: Optional[int] = None
    mode_ids: Optional[List[int]] = None


class AddGameFromIGDBRequest(BaseModel):
    igdb_id: int
    platform_ids: list[int]
    location_id: int | None = None
    tag_ids: list[int] = []
    condition: int | None = None
    order: int | None = None
