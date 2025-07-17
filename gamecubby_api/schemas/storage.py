from pydantic import BaseModel


class FileBase(BaseModel):
    game: str
    label: str
    path: str


class FileCreate(FileBase):
    pass


class FileResponse(FileBase):
    id: int

    class Config:
        from_attributes = True