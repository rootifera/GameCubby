from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models.genre import Genre
from ..models.mode import Mode


def format_igdb_cover_url(cover: Optional[dict]) -> Optional[str]:
    """
    Takes IGDB 'cover' dict and returns a formatted full-size cover URL.
    """
    if cover and cover.get("url"):
        return "https:" + cover["url"].replace("t_thumb", "t_cover_big")
    return None


def format_igdb_release_year(timestamp: Optional[int]) -> Optional[int]:
    """
    Converts IGDB 'first_release_date' timestamp to release year.
    """
    if timestamp:
        return datetime.fromtimestamp(timestamp).year
    return None


from datetime import datetime
from sqlalchemy.orm import Session
from ..models.genre import Genre
from ..models.mode import Mode

def format_igdb_cover_url(cover: dict | None) -> str | None:
    if cover and cover.get("url"):
        return "https:" + cover["url"].replace("t_thumb", "t_cover_big")
    return None


def format_igdb_release_year(ts: int | None) -> int | None:
    if ts:
        try:
            return datetime.fromtimestamp(ts).year
        except Exception:
            return None
    return None


def format_igdb_game(game: dict, db: Session | None = None) -> dict:
    cover_url = format_igdb_cover_url(game.get("cover"))
    release_year = format_igdb_release_year(game.get("first_release_date"))

    platforms = [
        {"id": p["id"], "name": p["name"]}
        for p in game.get("platforms", [])
        if p.get("id") and p.get("name")
    ]

    mode_ids = game.get("game_modes", [])
    if mode_ids and db:
        modes = db.query(Mode).filter(Mode.id.in_(mode_ids)).all()
        game_modes = [{"id": m.id, "name": m.name} for m in modes]
    else:
        game_modes = [{"id": m_id, "name": None} for m_id in mode_ids]

    genre_ids = game.get("genres", [])
    if genre_ids and db:
        genres = db.query(Genre).filter(Genre.id.in_(genre_ids)).all()
        game_genres = [{"id": g.id, "name": g.name} for g in genres]
    else:
        game_genres = [{"id": g_id, "name": None} for g_id in genre_ids]

    companies = game.get("companies", [])
    if companies:
        companies = [
            {"id": c["id"], "name": c["name"]}
            for c in companies if c.get("id") and c.get("name")
        ]

    collection = game.get("collection") if isinstance(game.get("collection"), dict) else None
    if collection and not collection.get("id"):
        collection = None

    igdb_tags = game.get("igdb_tags", [])
    if igdb_tags:
        igdb_tags = [
            {"id": t["id"], "name": t["name"]}
            for t in igdb_tags if t.get("id") and t.get("name")
        ]

    return {
        "id": game.get("id"),
        "name": game.get("name"),
        "cover_url": cover_url,
        "release_date": release_year,
        "platforms": platforms,
        "summary": game.get("summary"),
        "game_modes": game_modes,
        "genres": game_genres,
        "rating": int(game["rating"]) if game.get("rating") is not None else None,
        "updated_at": game.get("updated_at"),
        "companies": companies,
        "collection": collection,
        "igdb_tags": igdb_tags
    }
