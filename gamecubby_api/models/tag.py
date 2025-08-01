from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from ..models import Base


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    games = relationship("Game", secondary="game_tags", back_populates="tags")

    def __repr__(self):
        return f"<Tag(id={self.id}, name={self.name})>"
