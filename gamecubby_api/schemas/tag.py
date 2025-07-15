from pydantic import BaseModel

class Tag(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True