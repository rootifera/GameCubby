from datetime import datetime, UTC

def format_igdb_game(game):
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
    return {
        "id": game.get("id"),
        "name": game.get("name"),
        "cover_url": cover_url,
        "release_date": release_year,
        "platforms": platforms,
        "summary": game.get("summary"),
    }
