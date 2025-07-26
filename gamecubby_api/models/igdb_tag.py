from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from ..models import Base

game_igdb_tags = Table(
    "game_igdb_tags",
    Base.metadata,
    Column("game_id", Integer, ForeignKey("games.id"), primary_key=True),
    Column("igdb_tag_id", Integer, ForeignKey("igdb_tags.id"), primary_key=True),
)

class IGDBTag(Base):
    __tablename__ = "igdb_tags"

    id = Column(Integer, primary_key=True)  # IGDB's tag ID
    name = Column(String, nullable=False)

    def __repr__(self):
        return f"<IGDBTag(id={self.id}, name={self.name})>"
