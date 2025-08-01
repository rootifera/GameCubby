from sqlalchemy import Column, Integer, String
from ..models import Base


class Genre(Base):
    __tablename__ = "genres"
    id = Column(Integer, primary_key=True, autoincrement=False)
    name = Column(String, nullable=False, unique=True)
