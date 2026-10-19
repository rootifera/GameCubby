from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from gamecubby_api.models import Base
from gamecubby_api.models.collection import Collection
from gamecubby_api.models.company import Company
from gamecubby_api.models.game import Game
from gamecubby_api.models.game_company import GameCompany
from gamecubby_api.models.genre import Genre
from gamecubby_api.models.igdb_tag import IGDBTag
from gamecubby_api.models.location import Location
from gamecubby_api.models.mode import Mode
from gamecubby_api.models.platform import Platform
from gamecubby_api.models.playerperspective import PlayerPerspective
from gamecubby_api.models.tag import Tag
from gamecubby_api.utils.game_query import GAME_SCHEMA_LOAD_OPTIONS, games_to_schemas
from gamecubby_api.utils.location import get_location_path, location_path_resolver


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), engine


def _library(db, n_games):
    """n_games games, each with every relationship populated and a 3-deep location."""
    shelf = Location(name="Room"); db.add(shelf); db.flush()
    box = Location(name="Shelf", parent_id=shelf.id); db.add(box); db.flush()
    slot = Location(name="Box", parent_id=box.id); db.add(slot); db.flush()
    platforms = [Platform(id=i, name=f"P{i}") for i in (13, 6, 3)]  # inserted out of id order on purpose
    tags = [Tag(id=i, name=f"T{i}") for i in (9, 2, 5)]
    extra = [Mode(id=1, name="Single"), Genre(id=1, name="RPG"), PlayerPerspective(id=1, name="First"),
             IGDBTag(id=1, name="kw"), Collection(id=1, name="Series"), Company(id=1, name="Dev Co")]
    db.add_all(platforms + tags + extra)
    db.flush()
    for i in range(n_games):
        g = Game(name=f"Game {i}", igdb_id=i + 1, location_id=slot.id,
                 platforms=list(platforms), tags=list(tags), modes=[extra[0]], genres=[extra[1]],
                 playerperspectives=[extra[2]], igdb_tags=[extra[3]], collection=extra[4])
        db.add(g)
        db.flush()
        db.add(GameCompany(game_id=g.id, company_id=1, developer=True))
    db.commit()
    return slot


def _count_queries(engine, fn):
    n = 0

    def _c(*a, **k):
        nonlocal n
        n += 1

    event.listen(engine, "before_cursor_execute", _c)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _c)
    return n


def _load(db):
    games = db.query(Game).options(*GAME_SCHEMA_LOAD_OPTIONS).all()
    return games_to_schemas(db, games)


def test_query_count_does_not_grow_with_the_number_of_games():
    db_small, eng_small = _session()
    _library(db_small, 3)
    db_big, eng_big = _session()
    _library(db_big, 40)

    small = _count_queries(eng_small, lambda: _load(db_small))
    big = _count_queries(eng_big, lambda: _load(db_big))

    assert small == big  # constant: no per-game queries
    assert big <= 12     # games + one batched query per relationship + locations


def test_schemas_are_complete_and_ordered_by_id():
    db, _ = _session()
    _library(db, 2)
    schemas = _load(db)

    assert len(schemas) == 2
    g = schemas[0]
    assert [p.id for p in g.platforms] == [3, 6, 13]
    assert [t.id for t in g.tags] == [2, 5, 9]
    assert [m.name for m in g.modes] == ["Single"]
    assert g.collection.name == "Series"
    assert g.companies[0].company.name == "Dev Co" and g.companies[0].developer is True
    assert [p.name for p in g.location_path] == ["Room", "Shelf", "Box"]


def test_export_style_conversion_leaves_location_path_empty():
    db, _ = _session()
    _library(db, 1)
    games = db.query(Game).options(*GAME_SCHEMA_LOAD_OPTIONS).all()
    assert games_to_schemas(db, games, with_location_path=False)[0].location_path == []


def test_location_path_resolver_matches_get_location_path():
    db, _ = _session()
    slot = _library(db, 1)
    orphan = Location(name="Orphan", parent_id=9999)  # parent row doesn't exist
    db.add(orphan); db.flush()
    unplaced = Game(name="No location", igdb_id=500)
    placed_orphan = Game(name="Orphan game", igdb_id=501, location_id=orphan.id)
    db.add_all([unplaced, placed_orphan]); db.commit()

    resolve = location_path_resolver(db)
    for game in db.query(Game).all():
        assert resolve(game.location_id) == get_location_path(db, game.id)
    assert resolve(None) == [] and resolve(0) == []


def test_location_path_resolver_survives_a_parent_cycle():
    db, _ = _session()
    a = Location(name="A"); db.add(a); db.flush()
    b = Location(name="B", parent_id=a.id); db.add(b); db.flush()
    a.parent_id = b.id  # A -> B -> A
    db.commit()
    path = location_path_resolver(db)(a.id)  # must terminate
    assert sorted(p["name"] for p in path) == ["A", "B"]


def test_exports_are_sent_as_a_single_body_not_one_chunk_per_line():
    import json
    from gamecubby_api.utils import export

    db, _ = _session()
    _library(db, 3)

    resp = export.export_games_as_json(db)
    assert not hasattr(resp, "body_iterator")  # a plain Response, not a StreamingResponse
    rows = json.loads(resp.body)
    assert [r["name"] for r in rows] == ["Game 0", "Game 1", "Game 2"]
    assert rows[0]["location_path"] == []  # unchanged: exports have never included the path

    csv_resp = export.export_games_as_csv(db)
    assert csv_resp.body.decode().splitlines()[0].startswith("id,igdb_id,name")
    assert len(csv_resp.body.decode().splitlines()) == 4
    assert export.export_games_as_excel(db).body[:2] == b"PK"  # xlsx is a zip
