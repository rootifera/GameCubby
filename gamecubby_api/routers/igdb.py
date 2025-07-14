from dotenv import load_dotenv
from ..utils.formatting import format_igdb_game
from ..utils.external import get_igdb_token
load_dotenv()

import os
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()

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
