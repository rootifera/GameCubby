from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..utils.stats import get_overview_stats, get_health_stats
from ..schemas.stats import OverviewStats, HealthStats

router = APIRouter(prefix="/stats", tags=["Stats"])


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
    Library health (deduped by title under the hood), cached for 5 minutes.
    Returns:
    {
        "missing_cover": int,
        "missing_release_year": int,
        "no_platforms": int,
        "no_location": int,
        "untagged": int,
        "total_titles": int,
        "total_rows": int
    }
    """
    data = get_health_stats(db, use_cache=True)
    return HealthStats(**data)
