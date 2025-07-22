from sqlalchemy import Table, Column, Integer, ForeignKey
from ..models import Base

game_modes = Table(
    "game_modes",
    Base.metadata,
    Column("game_id", Integer, ForeignKey("games.id"), primary_key=True),
    Column("mode_id", Integer, ForeignKey("modes.id"), primary_key=True)
)
