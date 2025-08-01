import os
import httpx
from sqlalchemy.orm import Session
from ..models.playerperspective import PlayerPerspective
from ..utils.external import get_igdb_token


async def sync_player_perspectives(db: Session) -> int:
    """
    Fetch all player perspectives from IGDB and sync to DB.
    Returns the number of entries synced.
    """
    CLIENT_ID = os.getenv("CLIENT_ID")
    token = await get_igdb_token()

    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    query = "fields id, name; limit 100;"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.igdb.com/v4/player_perspectives",
            headers=headers,
            data=query
        )
    resp.raise_for_status()

    data = resp.json()
    for entry in data:
        existing = db.query(PlayerPerspective).filter_by(id=entry["id"]).first()
        if existing:
            if existing.name != entry["name"]:
                existing.name = entry["name"]
        else:
            db.add(PlayerPerspective(id=entry["id"], name=entry["name"]))
    db.commit()
    return len(data)


def get_player_perspective_by_id(db: Session, perspective_id: int) -> PlayerPerspective | None:
    return db.query(PlayerPerspective).filter(PlayerPerspective.id == perspective_id).first()
