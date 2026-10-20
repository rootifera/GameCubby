"""
"Find gaps": a read-only report on the numbering of ALL locations -- gaps (with the games either side),
duplicate numbers, and shelves that don't start at 1.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from gamecubby_api.db import get_db
from gamecubby_api.main import app
from gamecubby_api.models import Base
from gamecubby_api.models.game import Game
from gamecubby_api.models.location import Location
from gamecubby_api.utils import location as loc_utils
from gamecubby_api.utils.auth import get_current_admin


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _loc(db, name, parent=None):
    l = Location(name=name, parent_id=parent.id if parent else None)
    db.add(l)
    db.commit()
    return l


def _games(db, location, orders, names=None):
    out = []
    for i, o in enumerate(orders):
        g = Game(name=(names[i] if names else f"G{o}"), igdb_id=500 + db.query(Game).count(), location_id=location.id, order=o)
        db.add(g)
        db.commit()
        out.append(g)
    return out


def _by_path(report):
    return {" > ".join(p["path"]): p for p in report["problem_locations"]}


def test_a_clean_shelf_is_not_reported(db):
    shelf = _loc(db, "Front")
    _games(db, shelf, [1, 2, 3, 4])
    report = loc_utils.report_order_problems(db)
    assert report["problem_locations"] == []
    assert (report["locations_checked"], report["games_checked"], report["locations_ok"]) == (1, 4, 1)


def test_a_gap_names_the_missing_number_and_the_games_either_side(db):
    shelf = _loc(db, "B")
    _games(db, shelf, [1, 2, 3, 5, 6], names=["a", "b", "SimCity 2000", "SimLife", "e"])

    problem = _by_path(loc_utils.report_order_problems(db))["B"]

    assert len(problem["gaps"]) == 1
    gap = problem["gaps"][0]
    assert (gap["start"], gap["end"], gap["count"]) == (4, 4, 1)
    assert gap["after"]["name"] == "SimCity 2000" and gap["after"]["order"] == 3
    assert gap["before"]["name"] == "SimLife" and gap["before"]["order"] == 5
    assert problem["duplicates"] == [] and problem["starts_at"] is None


def test_a_run_of_missing_numbers_is_one_gap_and_two_gaps_are_two(db):
    shelf = _loc(db, "B")
    _games(db, shelf, [1, 2, 6, 7, 10])  # #3-#5 missing, #8-#9 missing

    gaps = _by_path(loc_utils.report_order_problems(db))["B"]["gaps"]

    assert [(g["start"], g["end"], g["count"]) for g in gaps] == [(3, 5, 3), (8, 9, 2)]


def test_duplicates_list_every_game_sharing_the_number(db):
    shelf = _loc(db, "C")
    _games(db, shelf, [4, 5, 5, 6], names=["x", "Quake", "Atomic Bomberman", "y"])  # (also doesn't start at 1)

    problem = _by_path(loc_utils.report_order_problems(db))["C"]

    assert len(problem["duplicates"]) == 1
    dup = problem["duplicates"][0]
    assert dup["order"] == 5 and sorted(g["name"] for g in dup["games"]) == ["Atomic Bomberman", "Quake"]


def test_a_shelf_not_starting_at_1_is_reported(db):
    _games(db, _loc(db, "Front"), [7])
    problem = _by_path(loc_utils.report_order_problems(db))["Front"]
    assert problem["starts_at"] == 7 and problem["gaps"] == [] and problem["duplicates"] == []


def test_every_location_in_the_library_is_checked_and_listed_by_path(db):
    kallax = _loc(db, "Kallax")
    a, b = _loc(db, "A", kallax), _loc(db, "B", kallax)
    other = _loc(db, "Cabinet")
    _games(db, a, [1, 3])
    _games(db, b, [1, 2])      # fine
    _games(db, other, [2, 3])  # starts at 2

    report = loc_utils.report_order_problems(db)

    assert [" > ".join(p["path"]) for p in report["problem_locations"]] == ["Cabinet", "Kallax > A"]
    assert (report["locations_checked"], report["locations_ok"], report["with_gaps"], report["not_starting_at_1"]) == (3, 1, 1, 1)


def test_summary_counts_each_kind_of_problem(db):
    _games(db, _loc(db, "gap"), [1, 3])
    _games(db, _loc(db, "dup"), [1, 1])
    _games(db, _loc(db, "start"), [2])
    _games(db, _loc(db, "all three"), [3, 3, 6])
    report = loc_utils.report_order_problems(db)
    assert (report["with_gaps"], report["with_duplicates"], report["not_starting_at_1"]) == (2, 2, 2)
    assert len(report["problem_locations"]) == 4


def test_games_without_an_order_or_a_location_are_ignored(db):
    shelf = _loc(db, "Front")
    _games(db, shelf, [1, None, 2])
    db.add(Game(name="nowhere", igdb_id=900, location_id=None, order=9))
    db.commit()
    report = loc_utils.report_order_problems(db)
    assert report["problem_locations"] == [] and report["games_checked"] == 2


def test_the_report_agrees_with_what_fill_gaps_would_change(db):
    kallax = _loc(db, "Kallax")
    for sub, orders in (("A", [1, 3, 4]), ("B", [2, 2, 5]), ("C", [1, 2])):
        _games(db, _loc(db, sub, kallax), orders)
    report = loc_utils.report_order_problems(db)
    plan = loc_utils.plan_order_renumbering(db, kallax.id, include_children=True)
    assert sum(p["fixable_changes"] for p in report["problem_locations"]) == plan["total_changed"]


def test_checking_changes_nothing(db):
    shelf = _loc(db, "Front")
    _games(db, shelf, [1, 3, 3])
    before = [(g.id, g.order) for g in db.query(Game).order_by(Game.id)]
    loc_utils.report_order_problems(db)
    assert [(g.id, g.order) for g in db.query(Game).order_by(Game.id)] == before


# ---- the HTTP route

@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_admin] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_route_returns_the_report_and_is_not_mistaken_for_a_location_id(db, client):
    _games(db, _loc(db, "B"), [1, 3])
    response = client.get("/locations/order-report")
    assert response.status_code == 200, "the /{location_id} route must not swallow this path"
    body = response.json()
    assert body["with_gaps"] == 1 and body["problem_locations"][0]["gaps"][0]["start"] == 2


def test_route_requires_an_admin(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).get("/locations/order-report")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code in (401, 403)
