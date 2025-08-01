from sqlalchemy import Column, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from ..models import Base


class GameCompany(Base):
    __tablename__ = "game_companies"

    game_id = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)

    developer = Column(Boolean, default=False)
    publisher = Column(Boolean, default=False)
    porting = Column(Boolean, default=False)
    supporting = Column(Boolean, default=False)

    company = relationship("Company", backref="game_links", passive_deletes=True)
