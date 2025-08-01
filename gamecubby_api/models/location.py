from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from ..models import Base


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    type = Column(String, nullable=True)  # E.g. 'bookshelf', 'shelf', 'box'

    parent = relationship("Location", remote_side=[id], backref="children")

    def __repr__(self):
        return f"<Location(id={self.id}, name={self.name}, parent_id={self.parent_id}, type={self.type})>"
