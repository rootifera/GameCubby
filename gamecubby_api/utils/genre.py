from sqlalchemy.orm import Session
from ..models.genre import Genre
from ..utils.external import get_igdb_token, _get_igdb_credentials, _post_with_retry


async def sync_genres(db: Session) -> list[dict]:
    client_id, _ = _get_igdb_credentials(db)
    token = await get_igdb_token()

    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
    }

    IGDB_GENRE_URL = "https://api.igdb.com/v4/genres"
    query = "fields id, name; limit 100;"

    resp = await _post_with_retry(IGDB_GENRE_URL, data=query, headers=headers)
    igdb_genres: list[dict] = resp.json()

    for genre in igdb_genres:
        existing = db.query(Genre).filter_by(id=genre["id"]).first()
        if existing:
            if existing.name != genre["name"]:
                existing.name = genre["name"]
        else:
            db.add(Genre(id=genre["id"], name=genre["name"]))

    db.commit()
    return igdb_genres
