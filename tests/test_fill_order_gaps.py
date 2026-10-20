"""
"Fill the gaps": renumber the games of a shelf (location) so they count 1..N left to right, with no gaps
and no duplicates. Each location is its own sequence. Manual, previewed, all-or-nothing.
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


def _games(db, location, orders, prefix="G"):
    out = []
    for i, o in enumerate(orders):
        g = Game(name=f"{prefix}{i}-{o}", igdb_id=1000 + len(out) + i, location_id=location.id, order=o)
        db.add(g)
        out.append(g)
    db.commit()
    return out


def _orders(db, location):
    return [g.order for g in db.query(Game).filter(Game.location_id == location.id).order_by(Game.id)]


def _apply(db, loc, children=False):
    plan = loc_utils.plan_order_renumbering(db, loc.id, children)
    return loc_utils.apply_order_renumbering(db, loc.id, children, plan["fingerprint"])


def test_the_example_from_the_shelf_1_3_4_5_6_8_9_10_becomes_1_to_8(db):
    shelf = _loc(db, "Front")
    _games(db, shelf, [1, 3, 4, 5, 6, 8, 9, 10])

    result = _apply(db, shelf)

    assert _orders(db, shelf) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert result["applied"] and result["total_changed"] == 7 and result["total_games"] == 8  # only game #1 stays


def test_preview_changes_nothing(db):
    shelf = _loc(db, "Front")
    _games(db, shelf, [1, 3, 4])

    plan = loc_utils.plan_order_renumbering(db, shelf.id)

    assert plan["applied"] is False and plan["total_changed"] == 2
    assert _orders(db, shelf) == [1, 3, 4]
    assert [(c["old"], c["new"]) for c in plan["locations"][0]["changes"]] == [(3, 2), (4, 3)]


def test_order_is_kept_even_if_games_were_added_in_a_different_sequence(db):
    shelf = _loc(db, "Front")
    games = _games(db, shelf, [9, 2, 5])  # added out of order

    _apply(db, shelf)

    assert {g.name: g.order for g in db.query(Game)} == {games[0].name: 3, games[1].name: 1, games[2].name: 2}


def test_games_sharing_a_number_are_split_in_the_order_they_were_added_and_reported(db):
    shelf = _loc(db, "C")
    quake, bomber, other = _games(db, shelf, [5, 5, 6])  # the real "Quake / Atomic Bomberman at 5" case

    plan = loc_utils.plan_order_renumbering(db, shelf.id)
    _apply(db, shelf)

    assert (db.get(Game, quake.id).order, db.get(Game, bomber.id).order, db.get(Game, other.id).order) == (1, 2, 3)
    ties = plan["locations"][0]["ties"]
    assert len(ties) == 1 and ties[0]["order"] == 5
    assert [(t["game_id"], t["new"]) for t in ties[0]["games"]] == [(quake.id, 1), (bomber.id, 2)]


def test_a_shelf_that_does_not_start_at_1_starts_at_1(db):
    shelf = _loc(db, "Front")
    _games(db, shelf, [7])
    _apply(db, shelf)
    assert _orders(db, shelf) == [1]


def test_games_without_an_order_are_left_alone(db):
    shelf = _loc(db, "Front")
    games = _games(db, shelf, [3, None, 5])

    _apply(db, shelf)

    assert [g.order for g in (db.get(Game, x.id) for x in games)] == [1, None, 2]


def test_only_the_selected_location_changes_unless_sub_locations_are_included(db):
    kallax = _loc(db, "Kallax")
    front = _loc(db, "Front", kallax)
    _games(db, kallax, [2, 5], "K")
    _games(db, front, [4, 9], "F")

    _apply(db, kallax, children=False)
    assert _orders(db, kallax) == [1, 2] and _orders(db, front) == [4, 9], "sub-locations are separate unless asked"

    _apply(db, kallax, children=True)
    assert _orders(db, front) == [1, 2]


def test_each_sub_location_is_its_own_sequence_not_one_combined_count(db):
    kallax = _loc(db, "Kallax")
    left, right = _loc(db, "Front Left", kallax), _loc(db, "Front Right", kallax)
    _games(db, left, [3, 6], "L")
    _games(db, right, [2, 8], "R")

    result = _apply(db, kallax, children=True)

    assert _orders(db, left) == [1, 2] and _orders(db, right) == [1, 2]
    assert {tuple(l["path"]) for l in result["locations"]} == {("Kallax", "Front Left"), ("Kallax", "Front Right")}


def test_games_in_other_branches_are_never_touched(db):
    a, b = _loc(db, "A"), _loc(db, "B")
    _games(db, a, [2, 4], "A")
    _games(db, b, [3, 9], "B")
    _apply(db, a, children=True)
    assert _orders(db, b) == [3, 9]


def test_running_it_twice_changes_nothing_the_second_time(db):
    shelf = _loc(db, "Front")
    _games(db, shelf, [1, 4, 4, 9])
    _apply(db, shelf)
    assert loc_utils.plan_order_renumbering(db, shelf.id)["total_changed"] == 0
    assert _orders(db, shelf) == [1, 2, 3, 4]


def test_names_and_everything_else_on_the_games_are_untouched(db):
    shelf = _loc(db, "Front")
    g = _games(db, shelf, [3])[0]
    g.updated_at, g.cover_cached = 1234, True
    db.commit()
    _apply(db, shelf)
    fresh = db.get(Game, g.id)
    assert (fresh.name, fresh.updated_at, fresh.cover_cached, fresh.igdb_id, fresh.location_id) == (g.name, 1234, True, g.igdb_id, shelf.id)


# ---- safety: what was previewed is what gets written

def test_applying_with_a_stale_preview_is_refused_and_writes_nothing(db):
    shelf = _loc(db, "Front")
    _games(db, shelf, [1, 3, 4])
    plan = loc_utils.plan_order_renumbering(db, shelf.id)

    db.add(Game(name="added meanwhile", igdb_id=9, location_id=shelf.id, order=2))  # someone changed the shelf
    db.commit()

    with pytest.raises(loc_utils.StaleOrderPlanError):
        loc_utils.apply_order_renumbering(db, shelf.id, False, plan["fingerprint"])
    assert sorted(_orders(db, shelf)) == [1, 2, 3, 4]


def test_a_failure_in_the_middle_of_writing_changes_nothing(db, monkeypatch):
    shelf = _loc(db, "Front")
    _games(db, shelf, [1, 3, 4])
    plan = loc_utils.plan_order_renumbering(db, shelf.id)

    real_execute = db.execute

    def failing_execute(statement, *a, **k):
        if "UPDATE" in str(statement).upper() or statement.__class__.__name__ == "Update":
            raise RuntimeError("simulated database failure")
        return real_execute(statement, *a, **k)

    monkeypatch.setattr(db, "execute", failing_execute)
    with pytest.raises(RuntimeError):
        loc_utils.apply_order_renumbering(db, shelf.id, False, plan["fingerprint"])
    monkeypatch.undo()
    assert _orders(db, shelf) == [1, 3, 4]


# ---- the HTTP route (the whole path: auth -> router -> database)

@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_admin] = lambda: object()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_route_preview_then_apply(db, client):
    shelf = _loc(db, "Front")
    _games(db, shelf, [1, 3, 4])

    preview = client.post(f"/locations/{shelf.id}/fill-order-gaps", json={"include_children": False, "apply": False})
    assert preview.status_code == 200 and preview.json()["applied"] is False and preview.json()["total_changed"] == 2
    assert _orders(db, shelf) == [1, 3, 4]

    applied = client.post(f"/locations/{shelf.id}/fill-order-gaps",
                          json={"apply": True, "fingerprint": preview.json()["fingerprint"]})
    assert applied.status_code == 200 and applied.json()["applied"] is True
    assert _orders(db, shelf) == [1, 2, 3]


def test_route_refuses_to_apply_without_a_preview_or_with_a_stale_one(db, client):
    shelf = _loc(db, "Front")
    _games(db, shelf, [1, 3])
    assert client.post(f"/locations/{shelf.id}/fill-order-gaps", json={"apply": True}).status_code == 400
    assert client.post(f"/locations/{shelf.id}/fill-order-gaps", json={"apply": True, "fingerprint": "deadbeef"}).status_code == 409
    assert _orders(db, shelf) == [1, 3]


def test_route_unknown_location_is_404(db, client):
    assert client.post("/locations/999/fill-order-gaps", json={}).status_code == 404


def test_route_requires_an_admin(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post("/locations/1/fill-order-gaps", json={})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code in (401, 403)
