from pydantic import BaseModel


class Collection(BaseModel):
    id: int
    igdb_id: int | None = None
    name: str

    class Config:
        from_attributes = True


class CollectionCreate(BaseModel):
    igdb_id: int | None = None
    name: str
