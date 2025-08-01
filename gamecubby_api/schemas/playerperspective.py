from pydantic import BaseModel


class PlayerPerspective(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
