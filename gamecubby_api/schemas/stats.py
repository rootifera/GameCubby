from pydantic import BaseModel
from typing import List, Optional


# ---------- Health ----------

class HealthStats(BaseModel):
    missing_cover: int
    missing_release_year: int
    no_platforms: int
    no_location: int
    untagged: int
    total_games_unique: int
    total_games: int

    class Config:
        from_attributes = True


# ---------- Summary (kept for compatibility/other screens) ----------

class SummaryStats(BaseModel):
    # Raw table totals
    games_rows: int
    platforms: int
    genres: int
    modes: int
    tags: int
    igdb_tags: int
    companies: int
    collections: int

    # Title-level rollup (dedupe-aware)
    titles: int
    titles_with_igdb: int
    titles_manual: int

    # Aggregates
    avg_rating_rows: float

    class Config:
        from_attributes = True


# ---------- Small reused shapes ----------

class YearBin(BaseModel):
    year: int
    count: int

    class Config:
        from_attributes = True


class PlatformCount(BaseModel):
    platform_id: int
    name: str
    count: int

    class Config:
        from_attributes = True


class GenreCount(BaseModel):
    genre_id: int
    name: str
    count: int

    class Config:
        from_attributes = True


# ---------- Overview (homepage) ----------

class ReleaseRange(BaseModel):
    oldest_year: Optional[int] = None
    newest_year: Optional[int] = None

    class Config:
        from_attributes = True


class RankedGenre(BaseModel):
    genre_id: int
    name: str
    count: int

    class Config:
        from_attributes = True


class RankedPlatform(BaseModel):
    platform_id: int
    name: str
    count: int

    class Config:
        from_attributes = True


class RankedPublisher(BaseModel):
    company_id: int
    name: str
    count: int

    class Config:
        from_attributes = True


class RankedDeveloper(BaseModel):
    company_id: int
    name: str
    count: int

    class Config:
        from_attributes = True


class RatedTitle(BaseModel):
    game_id: int
    igdb_id: int
    name: str
    rating: float

    class Config:
        from_attributes = True


class OverviewStats(BaseModel):
    # 1,2
    total_games: int
    total_games_unique: int

    # 3
    release_range: ReleaseRange

    # 4,5,6,7
    top_genres: List[RankedGenre]
    top_platforms: List[RankedPlatform]
    top_publishers: List[RankedPublisher]
    top_years: List[YearBin]

    # 8,9
    top_highest_rated: List[RatedTitle]
    top_lowest_rated: List[RatedTitle]

    # 10
    top_developers: List[RankedDeveloper]

    class Config:
        from_attributes = True
