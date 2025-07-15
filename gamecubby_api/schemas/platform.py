from pydantic import BaseModel

class Platform(BaseModel):
    id: int
    name: str
    slug: str | None = None

    class Config:
        orm_mode = True
