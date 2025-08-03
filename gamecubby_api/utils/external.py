import httpx
import time
from typing import Optional, Tuple
from fastapi import Depends
from sqlalchemy.orm import Session
from ..db import get_db
from .app_config import get_app_config_value

TOKEN_URL = "https://id.twitch.tv/oauth2/token"

_igdb_token: Optional[str] = None
_igdb_token_expiry: float = 0


def _get_igdb_credentials(db: Session) -> Tuple[str, str]:
    client_id = get_app_config_value(db, "CLIENT_ID")
    client_secret = get_app_config_value(db, "CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Missing IGDB credentials in app_config")
    return client_id, client_secret


async def get_igdb_token() -> str:
    global _igdb_token, _igdb_token_expiry

    if _igdb_token and time.time() < _igdb_token_expiry:
        return _igdb_token

    db = next(get_db())
    client_id, client_secret = _get_igdb_credentials(db)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
        )
    resp.raise_for_status()
    token_data = resp.json()
    _igdb_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)
    _igdb_token_expiry = time.time() + expires_in - 300
    return _igdb_token


async def fetch_igdb_game(igdb_id: int) -> Optional[dict]:
    db = next(get_db())
    client_id, _ = _get_igdb_credentials(db)
    token = await get_igdb_token()

    IGDB_URL = "https://api.igdb.com/v4/games"
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
    }
    query = (
        "fields id, name, summary, cover.url, first_release_date, platforms.id, platforms.name, "
        "collection, collection.name, game_modes, genres, rating, updated_at, "
        "player_perspectives, tags, involved_companies;"
        f" where id = {igdb_id};"
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(IGDB_URL, data=query, headers=headers)
    resp.raise_for_status()
    games = resp.json()
    return games[0] if games else None


async def fetch_igdb_collection(game_id: int) -> list[dict]:
    db = next(get_db())
    client_id, _ = _get_igdb_credentials(db)
    token = await get_igdb_token()

    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
    }

    COLLECTION_MEMBERSHIP_URL = "https://api.igdb.com/v4/collection_memberships"
    query = f"fields collection; where game = {game_id};"
    async with httpx.AsyncClient() as client:
        resp = await client.post(COLLECTION_MEMBERSHIP_URL, data=query, headers=headers)
    resp.raise_for_status()
    memberships = resp.json()
    collection_ids = [m["collection"] for m in memberships if m.get("collection")]

    if not collection_ids:
        return []

    COLLECTION_URL = "https://api.igdb.com/v4/collections"
    query = f"fields id, name; where id = ({','.join(str(cid) for cid in collection_ids)});"
    async with httpx.AsyncClient() as client:
        resp = await client.post(COLLECTION_URL, data=query, headers=headers)
    resp.raise_for_status()
    collections = resp.json()
    return [{"id": c["id"], "name": c["name"]} for c in collections]


async def fetch_igdb_companies(company_ids: list[int]) -> dict[int, str]:
    db = next(get_db())
    client_id, _ = _get_igdb_credentials(db)
    token = await get_igdb_token()

    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.igdb.com/v4/companies",
            headers=headers,
            data=f"fields id,name; where id = ({','.join(str(cid) for cid in company_ids)});",
        )
    resp.raise_for_status()
    return {c["id"]: c["name"] for c in resp.json()}


async def fetch_igdb_involved_companies(involved_ids: list[int]) -> list[dict]:
    db = next(get_db())
    client_id, _ = _get_igdb_credentials(db)
    token = await get_igdb_token()

    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.igdb.com/v4/involved_companies",
            headers=headers,
            data=f"fields company,developer,publisher,porting,supporting; where id = ({','.join(str(i) for i in involved_ids)});",
        )
    resp.raise_for_status()
    raw = resp.json()

    company_ids = [c["company"] for c in raw if "company" in c]
    company_map = await fetch_igdb_companies(company_ids)

    return [
        {
            "company_id": ic["company"],
            "name": company_map.get(ic["company"], "Unknown"),
            "developer": ic.get("developer", False),
            "publisher": ic.get("publisher", False),
            "porting": ic.get("porting", False),
            "supporting": ic.get("supporting", False),
        }
        for ic in raw if "company" in ic
    ]


async def search_igdb_games(name_query: str) -> list[dict]:
    db = next(get_db())
    client_id, _ = _get_igdb_credentials(db)
    token = await get_igdb_token()

    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}"
    }

    igdb_query = (
        f'search "{name_query}"; '
        "fields id, name, cover.url, first_release_date, summary, platforms.id, platforms.name; "
        "limit 50;"
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.igdb.com/v4/games",
            headers=headers,
            data=igdb_query
        )
    response.raise_for_status()
    return response.json()
