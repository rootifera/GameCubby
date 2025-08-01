from dotenv import load_dotenv
from ..utils.formatting import format_igdb_game
from ..utils.external import get_igdb_token, fetch_igdb_game, fetch_igdb_collection, fetch_igdb_involved_companies
from ..utils.platform import ensure_platforms_exist
from sqlalchemy.orm import Session
from ..utils.igdb_tag import upsert_igdb_tags
from ..db import get_db

load_dotenv()

import os
import httpx
from fastapi import APIRouter, Depends, HTTPException
from ..utils.auth import get_current_admin

router = APIRouter(tags=["IGDB"])

CLIENT_ID = os.getenv("CLIENT_ID")
IGDB_URL = "https://api.igdb.com/v4/games"
QUERY_LIMIT = int(os.getenv("QUERY_LIMIT", "50"))


@router.get("/search")
async def search_games(name: str, db: Session = Depends(get_db)):
    token = await get_igdb_token()
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }
    query = (
        f'search "{name}"; '
        'fields id, name, cover.url, first_release_date, platforms.id, platforms.name, summary, game_modes; '
        f'limit {QUERY_LIMIT};'
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(IGDB_URL, data=query, headers=headers)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    results = resp.json()
    formatted = [format_igdb_game(game, db) for game in results]
    return {"results": formatted}


@router.get("/game/{igdb_id}", dependencies=[Depends(get_current_admin)])
async def get_igdb_game_by_id(igdb_id: int, db: Session = Depends(get_db)):
    raw = await fetch_igdb_game(igdb_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Game not found on IGDB")

    game = format_igdb_game(raw, db)

    collections = await fetch_igdb_collection(igdb_id)
    game["collection"] = collections[0] if collections else None

    platforms = game.get("platforms", [])
    if platforms:
        ensure_platforms_exist(db, platforms)

    if "tags" in raw and raw["tags"]:
        tags = await upsert_igdb_tags(db, raw["tags"])
        db.commit()
        game["igdb_tags"] = [{"id": t.id, "name": t.name} for t in tags]
    else:
        game["igdb_tags"] = []

    if "involved_companies" in raw and raw["involved_companies"]:
        game["companies"] = await fetch_igdb_involved_companies(raw["involved_companies"])
    else:
        game["companies"] = []

    if game["companies"]:
        from gamecubby_api.utils.game_company import upsert_companies
        upsert_companies(db, game["companies"])
        db.commit()

    return game


@router.get("/collection_lookup/{game_id}", dependencies=[Depends(get_current_admin)])
async def collection_lookup(game_id: int):
    result = await fetch_igdb_collection(game_id)
    return {"collection": result}
