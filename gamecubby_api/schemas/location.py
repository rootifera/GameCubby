from pydantic import BaseModel


class Location(BaseModel):
    id: int
    name: str
    parent_id: int | None = None
    type: str | None = None

    class Config:
        from_attributes = True
