from pydantic import BaseModel


class IGDBTag(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
