from enum import Enum
from pydantic import BaseModel


class FileCategory(str, Enum):
    """High-level content categories for stored files (API-facing)."""
    audio_ost = "audio_ost"
    patch_update = "patch_update"
    saves = "saves"
    disc_image = "disc_image"
    screenshots = "screenshots"
    manuals_docs = "manuals_docs"
    artwork_covers = "artwork_covers"
    other = "other"


class FileBase(BaseModel):
    game: str
    label: str
    path: str
    category: FileCategory


class FileCreate(BaseModel):
    game: str
    label: str
    category: FileCategory


class FileResponse(FileBase):
    id: int

    class Config:
        from_attributes = True
