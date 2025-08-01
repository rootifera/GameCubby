from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from ..models import Base


class Platform(Base):
    __tablename__ = "platforms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=True)

    games = relationship("Game", secondary="game_platforms", back_populates="platforms")

    def __repr__(self):
        return f"<Platform(id={self.id}, name={self.name}, slug={self.slug})>"
