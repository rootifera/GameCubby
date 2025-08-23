from __future__ import annotations

import time
from typing import Dict, Tuple, List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from ..models.game import Game
from ..models.platform import Platform
from ..models.genre import Genre
from ..models.company import Company
from ..models.game_company import GameCompany  # to joinedload company
from ..models.tag import Tag
from ..models.mode import Mode
from ..models.collection import Collection
from ..models.igdb_tag import IGDBTag

# ----------------------------
# Simple in-memory cache (5m)
# ----------------------------

_CACHE_TTL_SECONDS = 300  # 5 minutes
_CACHE: Dict[str, Dict[str, object]] = {
    "overview": {"ts": 0.0, "data": None},
    "health": {"ts": 0.0, "data": None},
    # New: holds per-issue game ID lists computed alongside "health"
    "health_ids": {"ts": 0.0, "data": None},
}


def _get_cached(name: str) -> Optional[dict]:
    entry = _CACHE.get(name)
    if not entry:
        return None
    ts = entry.get("ts", 0.0) or 0.0
    if (time.time() - ts) <= _CACHE_TTL_SECONDS and entry.get("data") is not None:
        return entry["data"]  # type: ignore[return-value]
    return None


def _set_cached(name: str, data: dict) -> None:
    _CACHE[name] = {"ts": time.time(), "data": data}


# ----------------------------
# Shared helpers / dedupe key
# ----------------------------

def _title_key(g: Game) -> Tuple[str, int]:
    """
    Deduplication key for counting by title:
      - IGDB-backed titles (igdb_id not null/zero): ('igdb', igdb_id)
      - Manual entries (igdb_id is null or zero):   ('manual', id) -> each row is its own title
    """
    if g.igdb_id and g.igdb_id != 0:
        return ("igdb", int(g.igdb_id))
    return ("manual", int(g.id))


def _validate_dedupe(dedupe: str) -> str:
    if dedupe not in {"title", "none"}:
        raise HTTPException(status_code=422, detail="dedupe must be 'title' or 'none'")
    return dedupe


def _company_id(gc: GameCompany) -> Optional[int]:
    """
    Robustly fetch the company id from a GameCompany row.
    """
    cid = getattr(gc, "company_id", None)
    if isinstance(cid, int):
        return cid
    comp = getattr(gc, "company", None)
    cid = getattr(comp, "id", None) if comp is not None else None
    return int(cid) if isinstance(cid, int) else None


# --------------------------------------------------------
# HEALTH (cached facade + computation)
# --------------------------------------------------------

def compute_health_stats(db: Session, *, dedupe: str = "ignored") -> Dict[str, int]:
    """
    Health metrics with mixed dedupe:
      - Issue counters (missing cover/year, no platforms/location, untagged): **per row**
      - Totals: total_games (rows) and total_games_unique (titles via IGDB/manual key)

    Note: 'dedupe' arg kept for compatibility but ignored.

    Side-effect: also populates the "health_ids" cache with per-issue game ID lists
    so other endpoints can return exact game IDs without re-walking the DB.
    """
    games = (
        db.query(Game)
        .options(
            joinedload(Game.platforms),
            joinedload(Game.tags),
        )
        .all()
    )

    # Per-issue ID buckets (kept in-memory for /stats/health/* endpoints)
    ids = {
        "missing_cover": [],
        "missing_release_year": [],
        "no_platforms": [],
        "no_location": [],
        "untagged": [],
    }  # type: Dict[str, List[int]]

    # Counters (kept for the summary response)
    missing_cover = 0
    missing_release_year = 0
    no_platforms = 0
    no_location = 0
    untagged = 0

    for g in games:
        gid = int(g.id)

        if not (g.cover_url and str(g.cover_url).strip()):
            missing_cover += 1
            ids["missing_cover"].append(gid)

        if not (isinstance(g.release_date, int) and g.release_date > 0):
            missing_release_year += 1
            ids["missing_release_year"].append(gid)

        if not getattr(g, "platforms", []):
            no_platforms += 1
            ids["no_platforms"].append(gid)

        # if you want default location to count remove `or g.location_id == 1`
        if not g.location_id or g.location_id == 1:
            no_location += 1
            ids["no_location"].append(gid)

        if not getattr(g, "tags", []):
            untagged += 1
            ids["untagged"].append(gid)

    total_rows = len(games)
    total_titles = len({_title_key(g) for g in games})

    # Store detailed IDs in cache with same TTL
    _set_cached("health_ids", ids)

    return {
        "missing_cover": missing_cover,
        "missing_release_year": missing_release_year,
        "no_platforms": no_platforms,
        "no_location": no_location,
        "untagged": untagged,
        "total_games_unique": total_titles,  # title-deduped
        "total_games": total_rows,  # raw rows
    }


def get_health_stats(db: Session, *, use_cache: bool = True) -> Dict[str, int]:
    """
    Cached facade for health stats (5m TTL).
    Mixed dedupe: issues per-row, totals per-title.
    """
    cache_key = "health"
    if use_cache:
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached
    data = compute_health_stats(db)  # also populates "health_ids" cache
    _set_cached(cache_key, data)
    return data


def get_health_details(db: Session, *, use_cache: bool = True) -> Dict[str, List[int]]:
    """
    Returns the detailed game ID lists for each health issue category:
    {
      "missing_cover": [int, ...],
      "missing_release_year": [int, ...],
      "no_platforms": [int, ...],
      "no_location": [int, ...],
      "untagged": [int, ...]
    }

    Uses the same 5-minute TTL as get_health_stats. If details are not cached,
    it triggers a compute via compute_health_stats (which will also cache the summary).
    """
    if use_cache:
        cached = _get_cached("health_ids")
        if cached is not None:
            return cached  # type: ignore[return-value]

    # Ensure both summary and details are computed and cached
    compute_health_stats(db)
    details = _get_cached("health_ids")
    if details is None:
        # Shouldn't happen, but return empty structure to be safe
        return {
            "missing_cover": [],
            "missing_release_year": [],
            "no_platforms": [],
            "no_location": [],
            "untagged": [],
        }
    return details  # type: ignore[return-value]


# --------------------------------------------------------
# OVERVIEW (items 1–10 for homepage)
# --------------------------------------------------------

def get_overview_stats(db: Session, *, use_cache: bool = True) -> Dict[str, object]:
    """
    Build the complete overview payload with no query params.
    """
    if use_cache:
        cached = _get_cached("overview")
        if cached is not None:
            return cached

    games: List[Game] = (
        db.query(Game)
        .options(
            joinedload(Game.platforms),
            joinedload(Game.genres),
            joinedload(Game.companies).joinedload(GameCompany.company),
        )
        .all()
    )

    total_games = len(games)

    by_title: Dict[Tuple[str, int], dict] = {}
    for g in games:
        key = _title_key(g)
        rec = by_title.setdefault(key, {
            "rep_game_id": g.id,
            "igdb_id": g.igdb_id or 0,
            "name": g.name,
            "years": set(),
            "platform_ids": set(),
            "genre_ids": set(),
            "publisher_ids": set(),
            "developer_ids": set(),
            "ratings": [],
        })

        if g.igdb_id and g.igdb_id != 0:
            rec["igdb_id"] = int(g.igdb_id)
            rec["name"] = g.name or rec["name"]

        if isinstance(g.release_date, int) and g.release_date > 0:
            rec["years"].add(int(g.release_date))

        for p in getattr(g, "platforms", []):
            if p and isinstance(p.id, int):
                rec["platform_ids"].add(int(p.id))

        for gen in getattr(g, "genres", []):
            if gen and isinstance(gen.id, int):
                rec["genre_ids"].add(int(gen.id))

        for gc in getattr(g, "companies", []):
            cid = _company_id(gc)
            if cid is None:
                continue
            if getattr(gc, "publisher", False):
                rec["publisher_ids"].add(int(cid))
            if getattr(gc, "developer", False):
                rec["developer_ids"].add(int(cid))

        if isinstance(g.rating, int):
            rec["ratings"].append(int(g.rating))

    total_games_unique = len(by_title)

    per_title_year: List[int] = []
    for t in by_title.values():
        if t["years"]:
            per_title_year.append(min(t["years"]))
    oldest_year = min(per_title_year) if per_title_year else None
    newest_year = max(per_title_year) if per_title_year else None
    release_range = {"oldest_year": oldest_year, "newest_year": newest_year}

    def _top_counts(id_sets: List[set[int]], top_n: int) -> List[Tuple[int, int]]:
        counts: Dict[int, int] = {}
        for s in id_sets:
            for _id in s:
                counts[_id] = counts.get(_id, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]

    genre_counts = _top_counts([t["genre_ids"] for t in by_title.values()], top_n=5)
    genre_ids = [gid for gid, _ in genre_counts]
    genres = {g.id: g for g in db.query(Genre).filter(Genre.id.in_(genre_ids)).all()} if genre_ids else {}
    top_genres = [{"genre_id": gid, "name": genres.get(gid).name if gid in genres else "Unknown", "count": c}
                  for gid, c in genre_counts]

    platform_counts = _top_counts([t["platform_ids"] for t in by_title.values()], top_n=5)
    platform_ids = [pid for pid, _ in platform_counts]
    platforms = {p.id: p for p in
                 db.query(Platform).filter(Platform.id.in_(platform_ids)).all()} if platform_ids else {}
    top_platforms = [
        {"platform_id": pid, "name": platforms.get(pid).name if pid in platforms else "Unknown", "count": c}
        for pid, c in platform_counts]

    publisher_counts = _top_counts([t["publisher_ids"] for t in by_title.values()], top_n=5)
    publisher_ids = [cid for cid, _ in publisher_counts]
    publishers = {c.id: c for c in
                  db.query(Company).filter(Company.id.in_(publisher_ids)).all()} if publisher_ids else {}
    top_publishers = [
        {"company_id": cid, "name": publishers.get(cid).name if cid in publishers else "Unknown", "count": c}
        for cid, c in publisher_counts]

    developer_counts = _top_counts([t["developer_ids"] for t in by_title.values()], top_n=10)
    developer_ids = [cid for cid, _ in developer_counts]
    developers = {c.id: c for c in
                  db.query(Company).filter(Company.id.in_(developer_ids)).all()} if developer_ids else {}
    top_developers = [
        {"company_id": cid, "name": developers.get(cid).name if cid in developers else "Unknown", "count": c}
        for cid, c in developer_counts]

    year_counts: Dict[int, int] = {}
    for y in per_title_year:
        year_counts[y] = year_counts.get(y, 0) + 1
    top_years = [{"year": y, "count": c} for y, c in sorted(year_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]

    rated_titles: List[dict] = []
    for key, t in by_title.items():
        if t["ratings"]:
            avg = sum(t["ratings"]) / len(t["ratings"])
            rated_titles.append({
                "game_id": t["rep_game_id"],
                "igdb_id": t["igdb_id"],
                "name": t["name"],
                "rating": round(avg, 2),
            })
    top_highest_rated = sorted(rated_titles, key=lambda x: (-x["rating"], x["name"]))[:10]
    top_lowest_rated = sorted(
        [r for r in rated_titles if r["rating"] > 0],
        key=lambda x: (x["rating"], x["name"])
    )[:10]
    payload = {
        "total_games": total_games,
        "total_games_unique": total_games_unique,
        "release_range": release_range,
        "top_genres": top_genres,
        "top_platforms": top_platforms,
        "top_publishers": top_publishers,
        "top_years": top_years,
        "top_highest_rated": top_highest_rated,
        "top_lowest_rated": top_lowest_rated,
        "top_developers": top_developers,
    }

    _set_cached("overview", payload)
    return payload


# --------------------------------------------------------
# (Kept from earlier steps – used by older endpoints; safe to keep)
# --------------------------------------------------------

def compute_summary_stats(db: Session, *, dedupe: str = "title") -> Dict[str, int | float]:
    dedupe = _validate_dedupe(dedupe)

    totals = {
        "games_rows": db.query(Game).count(),
        "platforms": db.query(Platform).count(),
        "genres": db.query(Genre).count(),
        "modes": db.query(Mode).count(),
        "tags": db.query(Tag).count(),
        "igdb_tags": db.query(IGDBTag).count(),
        "companies": db.query(Company).count(),
        "collections": db.query(Collection).count(),
    }

    games = db.query(Game).all()
    title_keys = set(_title_key(g) for g in games) if dedupe == "title" else {("row", g.id) for g in games}
    with_igdb_titles = set(k for k in title_keys if k[0] == "igdb")
    manual_titles = set(k for k in title_keys if k[0] == "manual")

    ratings = [int(g.rating) for g in games if isinstance(g.rating, int)]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

    return {
        **totals,
        "titles": len(title_keys),
        "titles_with_igdb": len(with_igdb_titles),
        "titles_manual": len(manual_titles),
        "avg_rating_rows": avg_rating,
    }


def compute_games_by_year(
        db: Session,
        *,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        dedupe: str = "title",
) -> List[Dict[str, int]]:
    dedupe = _validate_dedupe(dedupe)
    games = db.query(Game).all()

    by_title: Dict[Tuple[str, int], int] = {}
    for g in games:
        if not isinstance(g.release_date, int) or g.release_date <= 0:
            continue
        key = _title_key(g) if dedupe == "title" else ("row", g.id)
        if key not in by_title:
            by_title[key] = g.release_date
        else:
            by_title[key] = min(by_title[key], g.release_date)

    counts: Dict[int, int] = {}
    for y in by_title.values():
        if year_from is not None and y < year_from:
            continue
        if year_to is not None and y > year_to:
            continue
        counts[y] = counts.get(y, 0) + 1

    return [{"year": year, "count": counts[year]} for year in sorted(counts)]


def compute_games_by_platform(
        db: Session,
        *,
        limit: Optional[int] = None,
        include_empty: bool = False,
        dedupe: str = "title",
) -> List[Dict[str, int | str]]:
    dedupe = _validate_dedupe(dedupe)
    games = db.query(Game).options(joinedload(Game.platforms)).all()

    title_platforms: Dict[Tuple[str, int], set[int]] = {}
    for g in games:
        key = _title_key(g) if dedupe == "title" else ("row", g.id)
        s = title_platforms.setdefault(key, set())
        for p in getattr(g, "platforms", []):
            if p and isinstance(p.id, int):
                s.add(p.id)

    counts: Dict[int, int] = {}
    for plats in title_platforms.values():
        if not plats and not include_empty:
            continue
        for pid in plats:
            counts[pid] = counts.get(pid, 0) + 1

    platforms = db.query(Platform).filter(Platform.id.in_(list(counts.keys()))).all() if counts else []
    items = [{"platform_id": p.id, "name": p.name, "count": counts.get(p.id, 0)} for p in platforms]
    items.sort(key=lambda x: x["count"], reverse=True)
    if limit:
        items = items[: int(limit)]
    return items


def compute_games_by_genre(
        db: Session,
        *,
        limit: Optional[int] = None,
        dedupe: str = "title",
) -> List[Dict[str, int | str]]:
    dedupe = _validate_dedupe(dedupe)
    games = db.query(Game).options(joinedload(Game.genres)).all()

    title_genres: Dict[Tuple[str, int], set[int]] = {}
    for g in games:
        key = _title_key(g) if dedupe == "title" else ("row", g.id)
        s = title_genres.setdefault(key, set())
        for gen in getattr(g, "genres", []):
            if gen and isinstance(gen.id, int):
                s.add(gen.id)

    counts: Dict[int, int] = {}
    for gens in title_genres.values():
        for gid in gens:
            counts[gid] = counts.get(gid, 0) + 1

    genres = db.query(Genre).filter(Genre.id.in_(list(counts.keys()))).all() if counts else []
    items = [{"genre_id": g.id, "name": g.name, "count": counts.get(g.id, 0)} for g in genres]
    items.sort(key=lambda x: x["count"], reverse=True)
    if limit:
        items = items[: int(limit)]
    return items


def force_refresh_health_stats(db: Session) -> Dict[str, int]:
    """
    Clears cached health stats and forces recomputation.
    Returns the freshly computed health summary.
    """
    _CACHE["health"] = {"ts": 0.0, "data": None}
    _CACHE["health_ids"] = {"ts": 0.0, "data": None}
    data = compute_health_stats(db)
    _set_cached("health", data)
    return data
