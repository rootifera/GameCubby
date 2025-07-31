from sqlalchemy import Table, Column, Integer, ForeignKey
from ..models import Base

game_platforms = Table(
    "game_platforms",
    Base.metadata,
    Column("game_id", Integer, ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("platform_id", Integer, ForeignKey("platforms.id", ondelete="CASCADE"), primary_key=True),
)
