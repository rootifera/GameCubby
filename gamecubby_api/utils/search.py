from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from ..db import get_db
from ..utils.db_tools import with_db  # ✅ NEW

from ..models.game import Game
from ..models.tag import Tag
from ..models.platform import Platform
from ..schemas.game import Game as GameSchema
from ..models.genre import Genre
from ..models.mode import Mode
from ..models.playerperspective import PlayerPerspective
from ..models.collection import Collection
from ..models.company import Company
from ..models.igdb_tag import IGDBTag
from ..models.location import Location


def search_games_basic(request: Request) -> list[GameSchema]:
    qp = request.query_params
    name = qp.get("name")
    year = qp.get("year")
    platform_id = qp.get("platform_id")
    tag_ids = qp.getlist("tag_ids")
    match_mode = qp.get("match_mode", "any")
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
            try:
                tag_ids_int = [int(tid) for tid in tag_ids]
            except ValueError:
                raise HTTPException(status_code=422, detail="Tag IDs must be integers")

            if match_mode == "all":
                for tid in tag_ids_int:
                    query = query.filter(Game.tags.any(Tag.id == tid))
            else:
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
        return [GameSchema.model_validate(g) for g in results]


def search_games_advanced(request: Request) -> list[GameSchema]:
    qp = request.query_params

    if not qp:
        raise HTTPException(status_code=400, detail="At least one search parameter must be provided")

    year = qp.get("year")
    year_min = qp.get("year_min")
    year_max = qp.get("year_max")

    if year and not year.isdigit():
        raise HTTPException(status_code=422, detail="year must be a number")
    if year_min and not year_min.isdigit():
        raise HTTPException(status_code=422, detail="year_min must be a number")
    if year_max and not year_max.isdigit():
        raise HTTPException(status_code=422, detail="year_max must be a number")

    include_manual = qp.get("include_manual")
    if include_manual not in [None, "true", "false", "only"]:
        raise HTTPException(
            status_code=422,
            detail="include_manual must be 'true', 'false', or 'only'"
        )

    filter_present = any([
        qp.get("name"),
        year,
        year_min,
        year_max,
        qp.get("platform_ids"),
        qp.get("tag_ids"),
        qp.get("genre_ids"),
        qp.get("mode_ids"),
        qp.get("perspective_ids"),
        qp.get("collection_id"),
        qp.get("company_id"),
        qp.get("igdb_tag_ids"),
        qp.get("location_id"),
        include_manual
    ])

    if not filter_present:
        raise HTTPException(status_code=400, detail="No valid filters provided")

    with with_db() as db:  # ✅ REPLACED get_db()
        query = db.query(Game)

        if name := qp.get("name"):
            query = query.filter(Game.name.ilike(f"%{name.strip().lower()}%"))

        if year:
            query = query.filter(Game.release_date == int(year))
        else:
            if year_min and year_max:
                query = query.filter(
                    Game.release_date >= int(year_min),
                    Game.release_date <= int(year_max)
                )
            elif year_min:
                query = query.filter(Game.release_date == int(year_min))
            elif year_max:
                query = query.filter(Game.release_date <= int(year_max))

        for pid in qp.getlist("platform_ids"):
            if pid.isdigit():
                query = query.filter(Game.platforms.any(Platform.id == int(pid)))

        for tid in qp.getlist("tag_ids"):
            if tid.isdigit():
                query = query.filter(Game.tags.any(Tag.id == int(tid)))

        for gid in qp.getlist("genre_ids"):
            if gid.isdigit():
                query = query.filter(Game.genres.any(Genre.id == int(gid)))

        for mid in qp.getlist("mode_ids"):
            if mid.isdigit():
                query = query.filter(Game.modes.any(Mode.id == int(mid)))

        for pid in qp.getlist("perspective_ids"):
            if pid.isdigit():
                query = query.filter(Game.playerperspectives.any(PlayerPerspective.id == int(pid)))

        if coll := qp.get("collection_id"):
            if coll.isdigit():
                query = query.filter(Game.collection_id == int(coll))

        if comp := qp.get("company_id"):
            if comp.isdigit():
                query = query.join(Game.companies).filter(Company.id == int(comp))

        for itid in qp.getlist("igdb_tag_ids"):
            if itid.isdigit():
                query = query.filter(Game.igdb_tags.any(IGDBTag.id == int(itid)))

        if loc := qp.get("location_id"):
            if loc.isdigit():
                query = query.filter(Game.location_id == int(loc))

        if include_manual == "true":
            pass
        elif include_manual == "false":
            query = query.filter(Game.igdb_id != 0)
        elif include_manual == "only":
            query = query.filter(Game.igdb_id == 0)

        if lim := qp.get("limit"):
            if lim.isdigit():
                query = query.limit(int(lim))
        if off := qp.get("offset"):
            if off.isdigit():
                query = query.offset(int(off))

        query = query.order_by(func.lower(Game.name))
        results = query.all()
        return [GameSchema.model_validate(g) for g in results]


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


def search_tag_suggestions(request: Request) -> list[str]:
    query_text = request.query_params.get("q", "").strip()
    if len(query_text) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    with with_db() as db:
        results = (
            db.query(Tag.name)
            .filter(Tag.name.ilike(f"%{query_text}%"))
            .order_by(func.lower(Tag.name))
            .limit(10)
            .all()
        )
        return [r[0] for r in results]


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
