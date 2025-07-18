from dotenv import load_dotenv
from ..utils.formatting import format_igdb_game
from ..utils.external import get_igdb_token, fetch_igdb_game, fetch_igdb_collection

load_dotenv()

import os
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["IGDB"])

CLIENT_ID = os.getenv("CLIENT_ID")
IGDB_URL = "https://api.igdb.com/v4/games"
QUERY_LIMIT = int(os.getenv("QUERY_LIMIT", "50"))

@router.get("/search")
async def search_games(name: str):
    token = await get_igdb_token()
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }
    query = (
        f'search "{name}"; '
        'fields id, name, cover.url, first_release_date, platforms.id, platforms.name, summary; '
        f'limit {QUERY_LIMIT};'
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(IGDB_URL, data=query, headers=headers)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    results = resp.json()
    return [format_igdb_game(game) for game in results]

@router.get("/game/{igdb_id}")
async def get_igdb_game_by_id(igdb_id: int):
    raw = await fetch_igdb_game(igdb_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Game not found on IGDB")
    game = format_igdb_game(raw)
    collections = await fetch_igdb_collection(igdb_id)
    if collections:
        game["collection"] = collections[0]
    else:
        game["collection"] = None
    return game



@router.get("/collection_lookup/{game_id}")
async def collection_lookup(game_id: int):
    result = await fetch_igdb_collection(game_id)
    return result