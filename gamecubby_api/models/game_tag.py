from sqlalchemy import Table, Column, Integer, ForeignKey
from ..models import Base

game_tags = Table(
    "game_tags",
    Base.metadata,
    Column("game_id", Integer, ForeignKey("games.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True)
)
