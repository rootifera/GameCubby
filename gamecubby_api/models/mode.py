from sqlalchemy import Column, Integer, String
from ..models import Base


class Mode(Base):
    __tablename__ = "modes"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    def __repr__(self):
        return f"<Mode(id={self.id}, name={self.name})>"
