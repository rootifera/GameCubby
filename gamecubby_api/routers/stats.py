from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..db import get_db
from ..utils.stats import get_overview_stats, get_health_stats, get_health_details, force_refresh_all_stats
from ..schemas.stats import OverviewStats, HealthStats
from ..utils.auth import get_current_admin

router = APIRouter(prefix="/stats", tags=["Stats"])


class IdList(BaseModel):
    ids: List[int]
    count: int


@router.get("/overview", response_model=OverviewStats)
def stats_overview(db: Session = Depends(get_db)) -> OverviewStats:
    """
    Homepage overview:
      1) Total Games
      2) Total Games (Unique)
      3) Release Range (oldest/newest)
      4) Top 5 Genres
      5) Top 5 Platforms
      6) Top 5 Publishers
      7) Top 5 Years (most releases)
      8) Top 10 Highest Rated games
      9) Top 10 Lowest Rated games
     10) Top 10 Developers
    Uses a 5-minute in-memory cache in utils.stats to avoid hammering the DB.
    """
    data = get_overview_stats(db, use_cache=True)
    return OverviewStats(**data)


@router.get("/health", response_model=HealthStats)
def stats_health(db: Session = Depends(get_db)) -> HealthStats:
    """
    Library health (summary), cached for 5 minutes.
    Response shape is unchanged to avoid breaking the WebUI.
    """
    data = get_health_stats(db, use_cache=True)
    return HealthStats(**data)


def _wrap_ids(ids: List[int]) -> IdList:
    return IdList(ids=ids, count=len(ids))


@router.get("/health/cover", response_model=IdList)
def stats_health_cover(db: Session = Depends(get_db)) -> IdList:
    """
    Game IDs that are missing cover.
    """
    details = get_health_details(db, use_cache=True)
    return _wrap_ids(details.get("missing_cover", []))


@router.get("/health/release_year", response_model=IdList)
def stats_health_release_year(db: Session = Depends(get_db)) -> IdList:
    """
    Game IDs that are missing release year.
    """
    details = get_health_details(db, use_cache=True)
    return _wrap_ids(details.get("missing_release_year", []))


@router.get("/health/platform", response_model=IdList)
def stats_health_platform(db: Session = Depends(get_db)) -> IdList:
    """
    Game IDs that have no platforms.
    """
    details = get_health_details(db, use_cache=True)
    return _wrap_ids(details.get("no_platforms", []))


@router.get("/health/location", response_model=IdList)
def stats_health_location(db: Session = Depends(get_db)) -> IdList:
    """
    Game IDs that have no location (or default location per current rule).
    """
    details = get_health_details(db, use_cache=True)
    return _wrap_ids(details.get("no_location", []))


@router.get("/health/tag", response_model=IdList)
def stats_health_tag(db: Session = Depends(get_db)) -> IdList:
    """
    Game IDs that have no tags.
    """
    details = get_health_details(db, use_cache=True)
    return _wrap_ids(details.get("untagged", []))


@router.post("/force_refresh", dependencies=[Depends(get_current_admin)])
def stats_force_refresh(db: Session = Depends(get_db)) -> dict:
    """
    Clears ALL stat caches and recomputes them immediately (admin-only).
    Does not return stats; just a confirmation.
    """
    force_refresh_all_stats(db)
    return {"detail": "Stats cache refreshed"}
