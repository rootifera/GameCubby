from pydantic import BaseModel


class Platform(BaseModel):
    id: int
    name: str
    slug: str | None = None

    class Config:
        from_attributes = True
