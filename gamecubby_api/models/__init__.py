from sqlalchemy.orm import declarative_base

Base = declarative_base()

from .collection import Collection
from .game_platform import game_platforms
from .game import Game
from .game_tag import game_tags
from .location import Location
from .platform import Platform
from .storage import GameFile
from .tag import Tag
from .company import Company
from .game_company import GameCompany
from .admin import AdminUser
from .genre import Genre
from .mode import Mode
from .playerperspective import PlayerPerspective
from .game_mode import game_modes
from .game_genre import game_genres
from .game_playerperspective import game_playerperspectives
from .igdb_tag import IGDBTag, game_igdb_tags
