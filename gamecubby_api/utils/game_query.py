"""
Helpers for turning many Game rows into `Game` response schemas without N+1 queries.

`GameSchema.model_validate(game)` touches eight relationships (platforms, tags,
collection, modes, genres, player perspectives, IGDB tags, companies -> company).
Left lazy, that is ~14 extra queries per game; with these options each relationship
is loaded for the whole result set in one batched query.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session, joinedload, selectinload

from ..models.game import Game
from ..models.game_company import GameCompany
from ..schemas.game import Game as GameSchema, LocationPathItem
from .location import location_path_resolver

# selectinload for collections (keeps LIMIT/OFFSET correct), joinedload for the
# many-to-one `collection`.
GAME_SCHEMA_LOAD_OPTIONS = (
    selectinload(Game.platforms),
    selectinload(Game.tags),
    joinedload(Game.collection),
    selectinload(Game.modes),
    selectinload(Game.genres),
    selectinload(Game.playerperspectives),
    selectinload(Game.igdb_tags),
    selectinload(Game.companies).joinedload(GameCompany.company),
)


_SORTED_BY_ID = ("platforms", "tags", "modes", "genres", "playerperspectives", "igdb_tags")


def _stable_order(item: GameSchema) -> None:
    """
    Give every list a defined order (by id). The lazy loads used before had no ORDER BY,
    so the order was whatever Postgres's plan returned; batched loading would shuffle it
    differently. Sorting by id matches what users saw for platforms/tags/genres/modes/
    perspectives, and makes the order stable between requests and between list/detail.
    (`companies` is left as loaded: it already comes back in insertion order, developer first.)
    """
    for name in _SORTED_BY_ID:
        getattr(item, name).sort(key=lambda x: x.id)


def games_to_schemas(db: Session, games: Iterable[Game], *, with_location_path: bool = True) -> list[GameSchema]:
    """
    Convert (eagerly loaded) games to response schemas.
    `with_location_path=False` leaves `location_path` empty (what the export has always done).
    """
    resolve = location_path_resolver(db) if with_location_path else None
    out: list[GameSchema] = []
    for g in games:
        item = GameSchema.model_validate(g)
        _stable_order(item)
        if resolve is not None:
            item.location_path = [LocationPathItem(**p) for p in resolve(g.location_id)]
        out.append(item)
    return out
