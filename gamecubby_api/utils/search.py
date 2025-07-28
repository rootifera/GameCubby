from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from ..db import get_db
from ..models.game import Game
from ..models.tag import Tag
from ..models.platform import Platform
from ..schemas.game import Game as GameSchema


def search_games_basic(request: Request) -> list[GameSchema]:
    qp = request.query_params

    name = qp.get("name")
    year = qp.get("year")
    platform_id = qp.get("platform_id")
    tag_ids = qp.getlist("tag_ids")
    match_mode = qp.get("match_mode", "any")
    limit = qp.get("limit")
    offset = qp.get("offset")

    db_gen = get_db()
    db: Session = next(db_gen)

    try:
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

    finally:
        db_gen.close()


def search_game_name_suggestions(request: Request) -> list[str]:
    query_text = request.query_params.get("q", "").strip()
    if len(query_text) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    db_gen = get_db()
    db: Session = next(db_gen)

    try:
        results = (
            db.query(Game.name)
            .filter(Game.name.ilike(f"%{query_text}%"))
            .order_by(func.lower(Game.name))
            .limit(10)
            .all()
        )
        return [r[0] for r in results]
    finally:
        db_gen.close()


def search_tag_suggestions(request: Request) -> list[str]:
    query_text = request.query_params.get("q", "").strip()
    if len(query_text) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    db_gen = get_db()
    db: Session = next(db_gen)

    try:
        results = (
            db.query(Tag.name)
            .filter(Tag.name.ilike(f"%{query_text}%"))
            .order_by(func.lower(Tag.name))
            .limit(10)
            .all()
        )
        return [r[0] for r in results]
    finally:
        db_gen.close()
