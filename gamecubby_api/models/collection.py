from sqlalchemy import Column, Integer, String
from ..models import Base


class Collection(Base):
    __tablename__ = "collections"

    id = Column(Integer, primary_key=True)
    igdb_id = Column(Integer, unique=True, nullable=True)  # can be null for manual
    name = Column(String, unique=True, nullable=False)

    def __repr__(self):
        return f"<Collection(id={self.id}, name={self.name}, igdb_id={self.igdb_id})>"
