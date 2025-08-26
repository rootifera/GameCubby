from pydantic import BaseModel, Field
from typing import Optional, List, Union
from .platform import Platform
from .tag import Tag
from .collection import Collection
from .genre import Genre
from .mode import Mode
from .playerperspective import PlayerPerspective
from .company import Company as CompanySchema
from .igdb_tag import IGDBTag as IGDBTagSchema


class AssignLocationRequest(BaseModel):
    location_id: int
    order: int | None = None


class GameCompany(BaseModel):
    company: CompanySchema
    developer: bool
    publisher: bool
    porting: bool
    supporting: bool

    class Config:
        from_attributes = True


class LocationPathItem(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class Game(BaseModel):
    id: int
    igdb_id: int
    name: str
    summary: Optional[str]
    release_date: Optional[int]
    cover_url: Optional[str]
    condition: Optional[int]
    location_path: List[LocationPathItem] = Field(default_factory=list)
    order: Optional[int]
    rating: Optional[int] = None
    updated_at: Optional[int] = None
    platforms: List[Platform] = Field(default_factory=list)
    tags: List[Tag] = Field(default_factory=list)
    collection: Optional[Collection] = None
    modes: List[Mode] = Field(default_factory=list)
    genres: List[Genre] = Field(default_factory=list)
    playerperspectives: List[PlayerPerspective] = Field(default_factory=list)
    igdb_tags: List[IGDBTagSchema] = Field(default_factory=list)
    companies: List[GameCompany] = Field(default_factory=list)

    class Config:
        from_attributes = True


class GameCreate(BaseModel):
    name: str
    summary: Optional[str] = None
    release_date: Optional[int] = None
    cover_url: Optional[str] = None
    condition: Optional[int] = None
    location_id: Optional[int] = None
    order: Optional[int] = None
    mode_ids: Optional[List[int]] = Field(default_factory=list)
    platform_ids: Optional[List[int]] = Field(default_factory=list)
    genre_ids: Optional[List[int]] = Field(default_factory=list)
    player_perspective_ids: Optional[List[int]] = Field(default_factory=list)
    rating: Optional[int] = None
    collection_id: Optional[int] = None
    tag_ids: Optional[List[Union[int, str]]] = Field(default_factory=list)
    company_ids: Optional[List[int]] = Field(default_factory=list)

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
    platform_ids: Optional[List[int]] = None
    genre_ids: Optional[List[int]] = None
    player_perspective_ids: Optional[List[int]] = None
    rating: Optional[int] = None
    tag_ids: Optional[List[Union[int, str]]] = None
    collection_id: Optional[int] = None
    company_ids: Optional[List[int]] = None


class AddGameFromIGDBRequest(BaseModel):
    igdb_id: int
    platform_ids: list[int]
    location_id: int | None = None
    tag_ids: list[Union[int, str]] = Field(default_factory=list)  # <-- changed here
    condition: int | None = None
    order: int | None = None


class PlatformPreview(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class GamePreview(BaseModel):
    id: int
    name: str
    cover_url: Optional[str] = None
    release_date: Optional[int] = None
    summary: Optional[str] = None
    platforms: List[PlatformPreview] = Field(default_factory=list)

    class Config:
        from_attributes = True


class GameIdName(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True