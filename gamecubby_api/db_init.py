import os
from sqlalchemy import create_engine
from .models import Base
from .models import platform, tag, game_tag, location, game, collection
from .models import game_platform
from .models.storage import GameFile

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gamecubby.db")
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
Base.metadata.create_all(bind=engine)
