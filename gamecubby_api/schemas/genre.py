from pydantic import BaseModel


class Genre(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
