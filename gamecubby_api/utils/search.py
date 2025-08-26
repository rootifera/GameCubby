from fastapi import Request, HTTPException
from sqlalchemy.sql import func

from ..utils.db_tools import with_db
from ..utils.location import get_location_path, get_descendant_location_ids_from_snapshot

from ..models.game import Game
from ..models.tag import Tag
from ..models.platform import Platform
from ..schemas.game import Game as GameSchema, LocationPathItem
from ..models.genre import Genre
from ..models.mode import Mode
from ..models.playerperspective import PlayerPerspective
from ..models.collection import Collection
from ..models.company import Company
from ..models.igdb_tag import IGDBTag
from ..models.location import Location
from ..models.game_company import GameCompany  # association obj for companies


def _validate_match_mode(value: str | None, field_name: str = "match_mode") -> str:
    mode = (value or "any").lower()
    if mode not in {"any", "all", "exact"}:
        raise HTTPException(status_code=422, detail=f"{field_name} must be one of: any, all, exact")
    return mode


def _parse_int_list(values: list[str]) -> list[int]:
    out: list[int] = []
    for v in values:
        if v is None:
            continue
        v = v.strip()
        if v == "":
            continue
        if not v.isdigit():
            raise HTTPException(status_code=422, detail="IDs must be integers")
        out.append(int(v))
    return out


def search_games_basic(request: Request) -> list[GameSchema]:
    qp = request.query_params
    name = qp.get("name")
    year = qp.get("year")
    platform_id = qp.get("platform_id")
    tag_ids = qp.getlist("tag_ids")
    match_mode = _validate_match_mode(qp.get("match_mode"), "match_mode")
    limit = qp.get("limit")
    offset = qp.get("offset")

    with with_db() as db:
        query = db.query(Game)

        if name:
            query = query.filter(Game.name.ilike(f"%{name.strip().lower()}%"))

        if year:
            if not year.isdigit():
                raise HTTPException(status_code=422, detail="Year must be a number")
            query = query.filter(Game.release_date == int(year))

        if platform_id:
            if not platform_id.isdigit():
                raise HTTPException(status_code=422, detail="Platform ID must be numeric")
            query = query.join(Game.platforms).filter(Platform.id == int(platform_id))

        if tag_ids:
            tag_ids_int = _parse_int_list(tag_ids)
            if match_mode == "all":
                for tid in tag_ids_int:
                    query = query.filter(Game.tags.any(Tag.id == tid))
            elif match_mode == "exact":
                for tid in tag_ids_int:
                    query = query.filter(Game.tags.any(Tag.id == tid))
                query = query.filter(~Game.tags.any(~Tag.id.in_(tag_ids_int)))
            else:  # any
                query = query.join(Game.tags).filter(Tag.id.in_(tag_ids_int))

        query = query.order_by(func.lower(Game.name))

        if limit:
            if not limit.isdigit():
                raise HTTPException(status_code=422, detail="Limit must be a number")
            query = query.limit(int(limit))

        if offset:
            if not offset.isdigit():
                raise HTTPException(status_code=422, detail="Offset must be a number")
            query = query.offset(int(offset))

        results = query.all()

        payload: list[GameSchema] = []
        with db:  # ensure same session for location lookups
            for g in results:
                item = GameSchema.model_validate(g)
                raw_path = get_location_path(db, g.id)
                item.location_path = [LocationPathItem(**p) for p in raw_path]
                payload.append(item)
        return payload


def search_games_advanced(request: Request) -> list[GameSchema]:
    qp = request.query_params
    if not qp:
        raise HTTPException(status_code=400, detail="At least one search parameter must be provided")

    # Years
    year = qp.get("year")
    year_min = qp.get("year_min")
    year_max = qp.get("year_max")
    if year and not year.isdigit():
        raise HTTPException(status_code=422, detail="year must be a number")
    if year_min and not year_min.isdigit():
        raise HTTPException(status_code=422, detail="year_min must be a number")
    if year_max and not year_max.isdigit():
        raise HTTPException(status_code=422, detail="year_max must be a number")

    # Match modes (tags keep 'match_mode' to avoid breaking)
    tag_match_mode = _validate_match_mode(qp.get("match_mode"), "match_mode")
    igdb_match_mode = _validate_match_mode(qp.get("igdb_match_mode"), "igdb_match_mode")
    platform_match_mode = _validate_match_mode(qp.get("platform_match_mode"), "platform_match_mode")
    genre_match_mode = _validate_match_mode(qp.get("genre_match_mode"), "genre_match_mode")
    mode_match_mode = _validate_match_mode(qp.get("mode_match_mode"), "mode_match_mode")
    perspective_match_mode = _validate_match_mode(qp.get("perspective_match_mode"), "perspective_match_mode")
    company_match_mode = _validate_match_mode(qp.get("company_match_mode"), "company_match_mode")

    include_manual = qp.get("include_manual")
    if include_manual not in [None, "true", "false", "only"]:
        raise HTTPException(status_code=422, detail="include_manual must be 'true', 'false', or 'only'")

    # Optional include-descendants toggle for location
    include_desc = qp.get("include_location_descendants")
    if include_desc not in [None, "true", "false"]:
        raise HTTPException(status_code=422, detail="include_location_descendants must be 'true' or 'false'")

    # Presence check
    filter_present = any([
        qp.get("name"),
        year, year_min, year_max,
        qp.get("platform_ids"),
        qp.get("tag_ids"),
        qp.get("genre_ids"),
        qp.get("mode_ids"),
        qp.get("perspective_ids"),
        qp.get("collection_id"),
        qp.get("company_id") or qp.get("company_ids"),
        qp.get("igdb_tag_ids"),
        qp.get("location_id"),
        include_manual
    ])
    if not filter_present:
        raise HTTPException(status_code=400, detail="No valid filters provided")

    with with_db() as db:
        query = db.query(Game)

        # Name
        if name := qp.get("name"):
            query = query.filter(Game.name.ilike(f"%{name.strip().lower()}%"))

        # Year and ranges
        if year:
            query = query.filter(
                Game.release_date >= int(year),
                Game.release_date <= int(year)
            )
        else:
            if year_min and year_max:
                query = query.filter(
                    Game.release_date >= int(year_min),
                    Game.release_date <= int(year_max)
                )
            elif year_min:
                query = query.filter(Game.release_date >= int(year_min))
            elif year_max:
                query = query.filter(Game.release_date <= int(year_max))

        # Platforms (any/all/exact)
        platform_ids = _parse_int_list(qp.getlist("platform_ids"))
        if platform_ids:
            if platform_match_mode == "all":
                for pid in platform_ids:
                    query = query.filter(Game.platforms.any(Platform.id == pid))
            elif platform_match_mode == "exact":
                for pid in platform_ids:
                    query = query.filter(Game.platforms.any(Platform.id == pid))
                query = query.filter(~Game.platforms.any(~Platform.id.in_(platform_ids)))
            else:  # any
                query = query.filter(Game.platforms.any(Platform.id.in_(platform_ids)))

        # Tags (any/all/exact)
        tag_ids = _parse_int_list(qp.getlist("tag_ids"))
        if tag_ids:
            if tag_match_mode == "all":
                for tid in tag_ids:
                    query = query.filter(Game.tags.any(Tag.id == tid))
            elif tag_match_mode == "exact":
                for tid in tag_ids:
                    query = query.filter(Game.tags.any(Tag.id == tid))
                query = query.filter(~Game.tags.any(~Tag.id.in_(tag_ids)))
            else:  # any
                query = query.filter(Game.tags.any(Tag.id.in_(tag_ids)))

        # Genres
        genre_ids = _parse_int_list(qp.getlist("genre_ids"))
        if genre_ids:
            if genre_match_mode == "all":
                for gid in genre_ids:
                    query = query.filter(Game.genres.any(Genre.id == gid))
            elif genre_match_mode == "exact":
                for gid in genre_ids:
                    query = query.filter(Game.genres.any(Genre.id == gid))
                query = query.filter(~Game.genres.any(~Genre.id.in_(genre_ids)))
            else:  # any
                query = query.filter(Game.genres.any(Genre.id.in_(genre_ids)))

        # Modes
        mode_ids = _parse_int_list(qp.getlist("mode_ids"))
        if mode_ids:
            if mode_match_mode == "all":
                for mid in mode_ids:
                    query = query.filter(Game.modes.any(Mode.id == mid))
            elif mode_match_mode == "exact":
                for mid in mode_ids:
                    query = query.filter(Game.modes.any(Mode.id == mid))
                query = query.filter(~Game.modes.any(~Mode.id.in_(mode_ids)))
            else:  # any
                query = query.filter(Game.modes.any(Mode.id.in_(mode_ids)))

        # Player perspectives
        perspective_ids = _parse_int_list(qp.getlist("perspective_ids"))
        if perspective_ids:
            if perspective_match_mode == "all":
                for ppid in perspective_ids:
                    query = query.filter(Game.playerperspectives.any(PlayerPerspective.id == ppid))
            elif perspective_match_mode == "exact":
                for ppid in perspective_ids:
                    query = query.filter(Game.playerperspectives.any(PlayerPerspective.id == ppid))
                query = query.filter(~Game.playerperspectives.any(~PlayerPerspective.id.in_(perspective_ids)))
            else:  # any
                query = query.filter(Game.playerperspectives.any(PlayerPerspective.id.in_(perspective_ids)))

        # Collection
        if coll := qp.get("collection_id"):
            if coll.isdigit():
                query = query.filter(Game.collection_id == int(coll))

        # Companies (multi + any/all/exact)
        company_ids: list[int] = []
        for cid in qp.getlist("company_ids"):
            if cid and cid.isdigit():
                company_ids.append(int(cid))
        for cid in qp.getlist("company_id"):
            if cid and cid.isdigit():
                company_ids.append(int(cid))
        if not company_ids:
            single = qp.get("company_id")
            if single and single.isdigit():
                company_ids.append(int(single))

        if company_ids:
            if company_match_mode == "all":
                for cid in company_ids:
                    query = query.filter(Game.companies.any(GameCompany.company_id == cid))
            elif company_match_mode == "exact":
                for cid in company_ids:
                    query = query.filter(Game.companies.any(GameCompany.company_id == cid))
                query = query.filter(~Game.companies.any(~GameCompany.company_id.in_(company_ids)))
            else:  # any
                query = query.filter(Game.companies.any(GameCompany.company_id.in_(company_ids)))

        # IGDB tags (any/all/exact)
        igdb_ids = _parse_int_list(qp.getlist("igdb_tag_ids"))
        if igdb_ids:
            if igdb_match_mode == "all":
                for itid in igdb_ids:
                    query = query.filter(Game.igdb_tags.any(IGDBTag.id == itid))
            elif igdb_match_mode == "exact":
                for itid in igdb_ids:
                    query = query.filter(Game.igdb_tags.any(IGDBTag.id == itid))
                query = query.filter(~Game.igdb_tags.any(~IGDBTag.id.in_(igdb_ids)))
            else:  # any
                query = query.filter(Game.igdb_tags.any(IGDBTag.id.in_(igdb_ids)))

        # Location (with optional descendants)
        if loc := qp.get("location_id"):
            if not loc.isdigit():
                raise HTTPException(status_code=422, detail="location_id must be a number")
            root = int(loc)
            if include_desc == "true":
                desc_ids = get_descendant_location_ids_from_snapshot(db, root)
                ids = [root] + desc_ids if desc_ids else [root]
                query = query.filter(Game.location_id.in_(ids))
            else:
                query = query.filter(Game.location_id == root)

        # Manual entries
        if include_manual == "true":
            pass
        elif include_manual == "false":
            query = query.filter(Game.igdb_id != 0)
        elif include_manual == "only":
            query = query.filter(Game.igdb_id == 0)

        # ORDER / LIMIT
        query = query.order_by(func.lower(Game.name))

        lim = qp.get("limit")
        off = qp.get("offset")
        if lim and lim.isdigit():
            query = query.limit(int(lim))
        if off and off.isdigit():
            query = query.offset(int(off))

        results = query.all()

        payload: list[GameSchema] = []
        for g in results:
            item = GameSchema.model_validate(g)
            raw_path = get_location_path(db, g.id)
            item.location_path = [LocationPathItem(**p) for p in raw_path]
            payload.append(item)
        return payload


def search_game_name_suggestions(request: Request) -> list[str]:
    query_text = request.query_params.get("q", "").strip()
    if len(query_text) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    with with_db() as db:
        results = (
            db.query(Game.name)
            .filter(Game.name.ilike(f"%{query_text}%"))
            .order_by(func.lower(Game.name))
            .limit(10)
            .all()
        )
        return [r[0] for r in results]


def search_tag_suggestions(request: Request) -> list[dict]:
    query_text = request.query_params.get("q", "").strip()
    if len(query_text) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    with with_db() as db:
        rows = (
            db.query(Tag)
            .filter(Tag.name.ilike(f"%{query_text}%"))
            .order_by(func.lower(Tag.name))
            .limit(10)
            .all()
        )
        return [{"id": t.id, "name": t.name} for t in rows]


def search_igdb_tag_suggestions(request: Request) -> list[dict]:
    q = request.query_params.get("q", "").strip()
    if len(q) < 2:
        raise HTTPException(400, "Query must be at least 2 characters")
    with with_db() as db:
        results = (
            db.query(IGDBTag)
            .filter(IGDBTag.name.ilike(f"%{q}%"))
            .order_by(func.lower(IGDBTag.name))
            .limit(10)
            .all()
        )
        return [{"id": r.id, "name": r.name} for r in results]


def search_genre_suggestions(request: Request) -> list[dict]:
    q = request.query_params.get("q", "").strip()
    if len(q) < 2:
        raise HTTPException(400, "Query must be at least 2 characters")
    with with_db() as db:
        results = (
            db.query(Genre)
            .filter(Genre.name.ilike(f"%{q}%"))
            .order_by(func.lower(Genre.name))
            .limit(10)
            .all()
        )
        return [{"id": r.id, "name": r.name} for r in results]


def search_mode_suggestions(request: Request) -> list[dict]:
    q = request.query_params.get("q", "").strip()
    if len(q) < 2:
        raise HTTPException(400, "Query must be at least 2 characters")
    with with_db() as db:
        results = (
            db.query(Mode)
            .filter(Mode.name.ilike(f"%{q}%"))
            .order_by(func.lower(Mode.name))
            .limit(10)
            .all()
        )
        return [{"id": r.id, "name": r.name} for r in results]


def search_collection_suggestions(request: Request) -> list[dict]:
    q = request.query_params.get("q", "").strip()
    if len(q) < 2:
        raise HTTPException(400, "Query must be at least 2 characters")
    with with_db() as db:
        results = (
            db.query(Collection)
            .filter(Collection.name.ilike(f"%{q}%"))
            .order_by(func.lower(Collection.name))
            .limit(10)
            .all()
        )
        return [{"id": r.id, "name": r.name} for r in results]


def search_company_suggestions(request: Request) -> list[dict]:
    q = request.query_params.get("q", "").strip()
    if len(q) < 2:
        raise HTTPException(400, "Query must be at least 2 characters")
    with with_db() as db:
        results = (
            db.query(Company)
            .filter(Company.name.ilike(f"%{q}%"))
            .order_by(func.lower(Company.name))
            .limit(10)
            .all()
        )
        return [{"id": r.id, "name": r.name} for r in results]
