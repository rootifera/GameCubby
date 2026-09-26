from pydantic import BaseModel, Field

from .platform import Platform


class WishlistLinkInput(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)


class WishlistLink(WishlistLinkInput):
    id: int

    class Config:
        from_attributes = True


class WishlistCreate(BaseModel):
    name: str = Field(min_length=1)
    igdb_id: int | None = None
    release_year: int | None = Field(default=None, ge=1, le=9999)
    cover_url: str | None = None
    platform_ids: list[int] = Field(default_factory=list)
    links: list[WishlistLinkInput] = Field(default_factory=list)


class WishlistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    release_year: int | None = Field(default=None, ge=1, le=9999)
    cover_url: str | None = None
    platform_ids: list[int] | None = None
    links: list[WishlistLinkInput] | None = None


class WishlistFromIGDBRequest(BaseModel):
    igdb_id: int
    platform_ids: list[int] = Field(default_factory=list)
    links: list[WishlistLinkInput] = Field(default_factory=list)


class WishlistPurchaseRequest(BaseModel):
    location_id: int | None = None
    condition: int | None = None
    order: int | None = None
    tag_ids: list[int | str] = Field(default_factory=list)


class WishlistResolveRequest(BaseModel):
    game_id: int = Field(gt=0)


class WishlistItem(BaseModel):
    id: int
    igdb_id: int | None = None
    name: str
    release_year: int | None = None
    cover_url: str | None = None
    status: str
    library_game_id: int | None = None
    platforms: list[Platform] = Field(default_factory=list)
    links: list[WishlistLink] = Field(default_factory=list)

    class Config:
        from_attributes = True
