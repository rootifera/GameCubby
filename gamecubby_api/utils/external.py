import os
import httpx
import time

TOKEN_URL = "https://id.twitch.tv/oauth2/token"

_igdb_token = None
_igdb_token_expiry = 0


async def get_igdb_token():
    global _igdb_token, _igdb_token_expiry

    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")

    if _igdb_token and time.time() < _igdb_token_expiry:
        return _igdb_token

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            params={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "client_credentials"
            }
        )
        resp.raise_for_status()
        token_data = resp.json()
        _igdb_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        _igdb_token_expiry = time.time() + expires_in - 300
        return _igdb_token


async def fetch_igdb_game(igdb_id: int):
    CLIENT_ID = os.getenv("CLIENT_ID")
    IGDB_URL = "https://api.igdb.com/v4/games"
    token = await get_igdb_token()
    headers = {
        "Client-ID": CLIENT_ID,
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
    if not games:
        return None
    return games[0]


async def fetch_igdb_collection(game_id: int):
    import os
    import httpx
    token = await get_igdb_token()
    CLIENT_ID = os.getenv("CLIENT_ID")
    COLLECTION_MEMBERSHIP_URL = "https://api.igdb.com/v4/collection_memberships"
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }
    query = f"fields collection; where game = {game_id};"
    async with httpx.AsyncClient() as client:
        resp = await client.post(COLLECTION_MEMBERSHIP_URL, data=query, headers=headers)
    resp.raise_for_status()
    memberships = resp.json()
    if not memberships:
        return []
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
    token = await get_igdb_token()
    headers = {
        "Client-ID": os.getenv("CLIENT_ID"),
        "Authorization": f"Bearer {token}"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.igdb.com/v4/companies",
            headers=headers,
            data=f"fields id,name; where id = ({','.join(str(cid) for cid in company_ids)});"
        )
        resp.raise_for_status()
        return {c["id"]: c["name"] for c in resp.json()}


async def fetch_igdb_involved_companies(involved_ids: list[int]) -> list[dict]:
    token = await get_igdb_token()
    headers = {
        "Client-ID": os.getenv("CLIENT_ID"),
        "Authorization": f"Bearer {token}"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.igdb.com/v4/involved_companies",
            headers=headers,
            data=f"fields company,developer,publisher,porting,supporting; where id = ({','.join(str(i) for i in involved_ids)});"
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
