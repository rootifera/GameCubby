from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from ..models.game_platform import game_platforms
from ..models.game_tag import game_tags
from ..models.game_mode import game_modes
from ..models.mode import Mode
from ..models import Base

class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    igdb_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    summary = Column(String, nullable=True)
    release_date = Column(Integer, nullable=True)
    cover_url = Column(String, nullable=True)
    condition = Column(Integer, nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    order = Column(Integer, nullable=True)

    location = relationship("Location")

    collection_id = Column(Integer, ForeignKey("collections.id"), nullable=True)
    collection = relationship("Collection")

    platforms = relationship("Platform", secondary=game_platforms, back_populates="games")
    tags = relationship("Tag", secondary=game_tags, back_populates="games")
    modes = relationship("Mode", secondary=game_modes, backref="games")

    def __repr__(self):
        return f"<Game(id={self.id}, name={self.name}, igdb_id={self.igdb_id})>"
