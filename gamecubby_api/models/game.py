from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from ..models.game_platform import game_platforms
from ..models.game_tag import game_tags
from ..models.game_mode import game_modes
from ..models.game_genre import game_genres
from ..models.genre import Genre
from ..models.mode import Mode
from ..models.playerperspective import PlayerPerspective
from ..models.game_playerperspective import game_playerperspectives
from ..models.igdb_tag import IGDBTag, game_igdb_tags
from ..models.game_company import GameCompany
from ..models import Base


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    igdb_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    summary = Column(String, nullable=True)
    release_date = Column(Integer, nullable=True)
    cover_url = Column(String, nullable=True)
    condition = Column(Integer, nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    order = Column(Integer, nullable=True)
    rating = Column(Integer, nullable=True)
    updated_at = Column(Integer, nullable=True)

    location = relationship("Location")

    collection_id = Column(Integer, ForeignKey("collections.id"), nullable=True)
    collection = relationship("Collection")

    platforms = relationship("Platform", secondary=game_platforms, back_populates="games")
    tags = relationship("Tag", secondary=game_tags, back_populates="games")
    modes = relationship("Mode", secondary=game_modes, backref="games")
    genres = relationship("Genre", secondary=game_genres, backref="games")
    igdb_tags = relationship(
        "IGDBTag",
        secondary="game_igdb_tags",
        backref="games"
    )
    companies = relationship(
        "GameCompany",
        backref="game",
        cascade="all, delete-orphan"
    )

    playerperspectives = relationship(
        "PlayerPerspective",
        secondary=game_playerperspectives,
        backref="games"
    )

    def __repr__(self):
        return f"<Game(id={self.id}, name={self.name}, igdb_id={self.igdb_id})>"
