from typing import List

from ..schemas.game import GamePreview, PlatformPreview
from ..utils.formatting import format_igdb_game
from ..utils.external import get_igdb_token, fetch_igdb_game, fetch_igdb_collection, fetch_igdb_involved_companies, \
    search_igdb_games
from ..utils.platform import ensure_platforms_exist
from sqlalchemy.orm import Session
from ..utils.igdb_tag import upsert_igdb_tags
from ..utils.app_config import get_int_config_value, get_or_create_query_limit

from fastapi import APIRouter, Depends, HTTPException, Query
from ..utils.auth import get_current_admin
from ..db import get_db

router = APIRouter(tags=["IGDB"])

QUERY_LIMIT = get_or_create_query_limit(next(get_db()))
IGDB_URL = "https://api.igdb.com/v4/games"


@router.get("/search", response_model=list[GamePreview])
async def igdb_game_search(q: str, db: Session = Depends(get_db)):
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    games_raw = await search_igdb_games(q)
    if not games_raw:
        return []

    return [
        GamePreview(
            id=game["id"],
            name=game["name"],
            cover_url=game["cover_url"],
            release_date=game["release_date"],
            summary=game["summary"],
            platforms=game["platforms"]
        )
        for game in (format_igdb_game(g, db) for g in games_raw)
    ]


@router.get("/game/{igdb_id}", dependencies=[Depends(get_current_admin)])
async def get_igdb_game_by_id(igdb_id: int, db: Session = Depends(get_db)):
    raw = await fetch_igdb_game(igdb_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Game not found on IGDB")

    game = format_igdb_game(raw, db)

    collections = await fetch_igdb_collection(igdb_id)
    game["collection"] = collections[0] if collections else None

    if game.get("platforms"):
        ensure_platforms_exist(db, game["platforms"])

    if raw.get("tags"):
        tags = await upsert_igdb_tags(db, raw["tags"])
        db.commit()
        game["igdb_tags"] = [{"id": t.id, "name": t.name} for t in tags]
    else:
        game["igdb_tags"] = []

    if raw.get("involved_companies"):
        companies = await fetch_igdb_involved_companies(raw["involved_companies"])
        game["companies"] = companies

        from gamecubby_api.utils.game_company import upsert_companies
        upsert_companies(db, companies)
        db.commit()
    else:
        game["companies"] = []

    return game
