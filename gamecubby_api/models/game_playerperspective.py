from sqlalchemy import Table, Column, Integer, ForeignKey
from ..models import Base

game_playerperspectives = Table(
    "game_playerperspectives",
    Base.metadata,
    Column("game_id", Integer, ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("perspective_id", Integer, ForeignKey("playerperspectives.id", ondelete="CASCADE"), primary_key=True),
)
