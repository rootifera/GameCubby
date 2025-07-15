from sqlalchemy import Column, Integer, String, Date, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from ..models import Base

class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    igdb_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    summary = Column(String, nullable=True)
    release_date = Column(Date, nullable=True)
    cover_url = Column(String, nullable=True)
    played = Column(Boolean, default=False)
    condition = Column(Integer, nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    order = Column(Integer, nullable=True)

    location = relationship("Location")

    def __repr__(self):
        return f"<Game(id={self.id}, name={self.name}, igdb_id={self.igdb_id})>"
