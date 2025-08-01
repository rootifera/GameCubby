from sqlalchemy import Column, Integer, String
from ..models import Base


class PlayerPerspective(Base):
    __tablename__ = "playerperspectives"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    def __repr__(self):
        return f"<PlayerPerspective(id={self.id}, name={self.name})>"
