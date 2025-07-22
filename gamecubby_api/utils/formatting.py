from datetime import datetime
from sqlalchemy.orm import Session
from ..models.mode import Mode
from ..models.genre import Genre

def format_igdb_game(game, db: Session):
    cover_url = None
    if game.get("cover") and game["cover"].get("url"):
        cover_url = "https:" + game["cover"]["url"].replace("t_thumb", "t_cover_big")
    release_year = None
    if game.get("first_release_date"):
        release_year = datetime.fromtimestamp(game["first_release_date"]).year
    platforms = [
        {"id": p["id"], "name": p["name"]}
        for p in game.get("platforms", [])
        if p.get("id") and p.get("name")
    ]

    # Modes
    mode_ids = game.get("game_modes", [])
    if mode_ids and db:
        modes = db.query(Mode).filter(Mode.id.in_(mode_ids)).all()
        game_modes = [{"id": m.id, "name": m.name} for m in modes]
    else:
        game_modes = [{"id": m_id, "name": None} for m_id in mode_ids]

    # Genres
    genre_ids = game.get("genres", [])
    if genre_ids and db:
        genres = db.query(Genre).filter(Genre.id.in_(genre_ids)).all()
        game_genres = [{"id": g.id, "name": g.name} for g in genres]
    else:
        game_genres = [{"id": g_id, "name": None} for g_id in genre_ids]

    return {
        "id": game.get("id"),
        "name": game.get("name"),
        "cover_url": cover_url,
        "release_date": release_year,
        "platforms": platforms,
        "summary": game.get("summary"),
        "game_modes": game_modes,
        "genres": game_genres,
    }