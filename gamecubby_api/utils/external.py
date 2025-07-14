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
