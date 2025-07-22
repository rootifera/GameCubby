from pydantic import BaseModel


class Mode(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
