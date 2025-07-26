from sqlalchemy import Column, Integer, String
from ..models import Base

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)  # IGDB company ID
    name = Column(String, nullable=False)

    def __repr__(self):
        return f"<Company(id={self.id}, name={self.name})>"
