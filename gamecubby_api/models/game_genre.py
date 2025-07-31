from sqlalchemy import Table, Column, Integer, ForeignKey
from ..models import Base

game_genres = Table(
    "game_genres",
    Base.metadata,
    Column("game_id", Integer, ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", Integer, ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)
