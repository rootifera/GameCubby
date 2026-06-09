from enum import Enum as PyEnum

from sqlalchemy import BigInteger, Column, Integer, String, Enum
from ..models import Base


class FileCategory(PyEnum):
    """High-level content categories for stored files."""
    audio_ost = "audio_ost"
    patch_update = "patch_update"
    saves = "saves"
    disc_image = "disc_image"
    screenshots = "screenshots"
    manuals_docs = "manuals_docs"
    artwork_covers = "artwork_covers"
    other = "other"


class GameFile(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True)
    game = Column(String(180))
    label = Column(String(100))
    path = Column(String(500), unique=True)
    storage_backend = Column(String(20), nullable=False, default="local", server_default="local")
    object_key = Column(String(1024), nullable=True)
    size = Column(BigInteger, nullable=True)
    content_type = Column(String(255), nullable=True)

    category = Column(
        Enum(FileCategory, name="file_category"),
        nullable=False,
        default=FileCategory.other,
    )

    def __repr__(self):
        cat = getattr(self.category, "value", self.category)
        return f"<File(id={self.id}, game='{self.game}', label='{self.label}', category='{cat}')>"
