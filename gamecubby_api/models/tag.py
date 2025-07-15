from sqlalchemy import Column, Integer, String
from ..models import Base

class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    def __repr__(self):
        return f"<Tag(id={self.id}, name={self.name})>"
