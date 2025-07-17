from sqlalchemy import Column, Integer, String
from ..models import Base


class GameFile(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True)
    game = Column(String(180))
    label = Column(String(100))
    path = Column(String(500), unique=True)

    def __repr__(self):
        return f"<File(id={self.id}, game='{self.game}', label='{self.label}')>"