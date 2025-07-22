import httpx
from sqlalchemy.orm import Session
from ..models.genre import Genre
from ..utils.external import get_igdb_token
import os

async def sync_genres(db: Session):
    CLIENT_ID = os.getenv("CLIENT_ID")
    token = await get_igdb_token()
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }
    IGDB_GENRE_URL = "https://api.igdb.com/v4/genres"
    query = "fields id, name; limit 100;"
    async with httpx.AsyncClient() as client:
        resp = await client.post(IGDB_GENRE_URL, data=query, headers=headers)
    resp.raise_for_status()
    igdb_genres = resp.json()
    for genre in igdb_genres:
        existing = db.query(Genre).filter_by(id=genre["id"]).first()
        if existing:
            if existing.name != genre["name"]:
                existing.name = genre["name"]
        else:
            db.add(Genre(id=genre["id"], name=genre["name"]))
    db.commit()
    return igdb_genres
