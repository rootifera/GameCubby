from collections import defaultdict
from typing import Optional, List, DefaultDict, Tuple
from sqlalchemy import func, update
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..models.location import Location
from ..models.game import Game


def create_location(session: Session, name: str, parent_id: Optional[int] = None,
                    type: Optional[str] = None) -> Location:
    location = Location(name=name, parent_id=parent_id, type=type)
    session.add(location)
    session.commit()
    session.refresh(location)
    return location


def get_location(session: Session, location_id: int) -> Optional[Location]:
    return session.query(Location).filter_by(id=location_id).first()


def list_top_locations(session: Session) -> list[Location]:
    return session.query(Location).filter_by(parent_id=None).order_by(Location.name).all()


def list_child_locations(session: Session, parent_id: int) -> list[Location]:
    return session.query(Location).filter_by(parent_id=parent_id).order_by(Location.name).all()


def list_all_locations(session: Session) -> list[Location]:
    return session.query(Location).order_by(Location.name).all()


def get_location_path(session: Session, game_id: int) -> list[dict]:
    """
    Returns complete location path from root to game's location.
    Guaranteed order: [root, ..., parent, current].
    Returns an empty list if game has no location.
    """
    game = session.query(Game).filter_by(id=game_id).first()
    if not game or not game.location_id:
        return []

    location_ids = []
    current_id = game.location_id

    while current_id:
        location_ids.append(current_id)
        parent = session.query(Location.parent_id).filter_by(id=current_id).first()
        current_id = parent[0] if parent else None

    locations = session.query(Location).filter(Location.id.in_(location_ids)).all()
    loc_dict = {loc.id: loc for loc in locations}

    return [
        {"id": loc.id, "name": loc.name}
        for loc_id in reversed(location_ids)
        if (loc := loc_dict.get(loc_id))
    ]


def location_path_resolver(session: Session):
    """
    Batch version of `get_location_path` for listing many games.

    Reads the (small) locations table once and returns `path_for(location_id)`, which
    builds the [root, ..., current] path in memory -- instead of 3+ queries per game.
    Produces the same output as `get_location_path`.
    """
    rows = session.query(Location.id, Location.name, Location.parent_id).all()
    by_id = {r.id: (r.name, r.parent_id) for r in rows}

    def path_for(location_id: Optional[int]) -> list[dict]:
        if not location_id:
            return []
        chain: list[int] = []
        seen: set[int] = set()
        current = location_id
        while current and current not in seen:  # `seen` guards against a parent cycle
            seen.add(current)
            chain.append(current)
            entry = by_id.get(current)
            current = entry[1] if entry else None
        return [{"id": loc_id, "name": by_id[loc_id][0]} for loc_id in reversed(chain) if loc_id in by_id]

    return path_for


def get_default_location_id(session: Session) -> Optional[int]:
    default = session.query(Location).filter_by(name="Default Storage").first()
    return default.id if default else None


def delete_location(session: Session, location_id: int) -> bool:
    """
    Delete a location ONLY if:
      - it exists,
      - it has NO child locations,
      - and NO games are assigned to it.

    Returns:
        True  -> deleted
        False -> not deleted (doesn't exist, has children, or has games)
    """
    loc = session.query(Location).filter_by(id=location_id).first()
    if not loc:
        return False

    has_children = session.query(Location.id).filter_by(parent_id=location_id).first() is not None
    if has_children:
        return False

    has_games = session.query(Game.id).filter_by(location_id=location_id).first() is not None
    if has_games:
        return False

    session.delete(loc)
    session.commit()
    return True


def rename_location(session: Session, location_id: int, new_name: str) -> Optional[Location]:
    """
    Rename a location (name only). Returns the updated Location or None if not found.
    Raises ValueError if new_name is empty/whitespace.
    """
    loc = session.query(Location).filter_by(id=location_id).first()
    if not loc:
        return None

    clean = (new_name or "").strip()
    if not clean:
        raise ValueError("Location name cannot be empty")

    loc.name = clean
    session.commit()
    session.refresh(loc)
    return loc


def migrate_location_games(session: Session, source_location_id: int, target_location_id: int) -> int:
    """
    Bulk-migrate all games from source_location_id to target_location_id.

    Returns:
        int -> number of games updated.

    Raises:
        ValueError -> if target location doesn't exist, or source==target.
    """
    if source_location_id == target_location_id:
        raise ValueError("Source and target locations must be different")

    target = session.query(Location.id).filter_by(id=target_location_id).first()
    if not target:
        raise ValueError("Target location does not exist")

    affected = (
        session.query(Game)
        .filter(Game.location_id == source_location_id)
        .update({Game.location_id: target_location_id}, synchronize_session=False)
    )
    session.commit()
    return int(affected or 0)


def get_descendant_location_ids_from_snapshot(session: Session, root_id: int) -> List[int]:
    """
    Compute ALL descendant location IDs under `root_id` using a single snapshot
    query of the entire locations table, then in-memory BFS over a parent->children
    map. Excludes `root_id` itself.

    This avoids multiple DB roundtrips and works regardless of ORM row/tuple quirks.
    """
    rows: list[tuple[int, int | None]] = [
        (loc.id, loc.parent_id) for loc in session.query(Location.id, Location.parent_id).all()
    ]

    children_map: DefaultDict[int, List[int]] = defaultdict(list)
    for loc_id, parent_id in rows:
        if parent_id is not None:
            children_map[parent_id].append(loc_id)

    descendants: List[int] = []
    frontier: List[int] = children_map.get(root_id, []).copy()

    while frontier:
        next_frontier: List[int] = []
        for lid in frontier:
            descendants.append(lid)
            kids = children_map.get(lid, [])
            if kids:
                next_frontier.extend(kids)
        frontier = next_frontier

    return descendants


def get_descendant_location_ids(session, root_id: int) -> list[int]:
    """
    Returns all descendant location IDs under root_id (excludes root_id).
    Implemented with SQLAlchemy Core recursive CTE (no raw SQL).
    """
    from sqlalchemy import select
    from sqlalchemy.orm import aliased
    from ..models.location import Location

    sub = select(Location.id).where(Location.parent_id == root_id).cte(name="sub", recursive=True)

    L = aliased(Location)

    sub = sub.union_all(
        select(L.id).where(L.parent_id == sub.c.id)
    )

    rows = session.execute(select(sub.c.id)).scalars().all()
    return list(rows)


def list_games_id_name_by_location(session: Session, location_id: int) -> List[Tuple[int, str]]:
    """
    Return (id, name) pairs for games assigned exactly to the given location_id.
    Sorted case-insensitively by name. Lightweight (selects only two columns).
    """
    rows = (
        session.query(Game.id, Game.name)
        .filter(Game.location_id == location_id)
        .order_by(func.lower(Game.name))
        .all()
    )
    return [(r[0], r[1]) for r in rows]


# ----------------------------------------------------------------------------------------------
# "Fill the gaps": renumber the games of a location so their order runs 1..N
# ----------------------------------------------------------------------------------------------

class StaleOrderPlanError(Exception):
    """The data changed between the preview and the apply."""


def _order_location_ids(session: Session, root_id: int, include_children: bool) -> List[int]:
    ids = [root_id]
    if include_children:
        ids += get_descendant_location_ids_from_snapshot(session, root_id)
    return ids


def plan_order_renumbering(session: Session, root_id: int, include_children: bool = False) -> dict:
    """
    Work out (without writing anything) how to renumber the games of a location so that, left to
    right, their order numbers are 1, 2, 3, ... with no gaps and no duplicates.

    - Each location is its own sequence (a shelf and the boxes on it are numbered separately).
    - Games are kept in their current order; games that share a number are split in the order they
      were added to the library (lowest game id first) and reported under `ties`.
    - Games without an order are left alone.
    - `fingerprint` identifies exactly this set of changes: applying requires the fingerprint of
      the preview, so what was shown is what gets written.
    """
    import hashlib

    ids = _order_location_ids(session, root_id, include_children)
    path_for = location_path_resolver(session)
    rows = (
        session.query(Game.id, Game.name, Game.location_id, Game.order)
        .filter(Game.location_id.in_(ids), Game.order.isnot(None))
        .all()
    )
    by_location: DefaultDict[int, list] = defaultdict(list)
    for row in rows:
        by_location[row.location_id].append(row)

    locations = []
    all_changes: list[tuple[int, int, int]] = []
    for location_id in ids:
        games = sorted(by_location.get(location_id, []), key=lambda r: (r.order, r.id))
        if not games:
            continue
        changes, groups = [], defaultdict(list)
        for new_order, row in enumerate(games, start=1):
            groups[row.order].append((row, new_order))
            if row.order != new_order:
                changes.append({"game_id": row.id, "name": row.name, "old": row.order, "new": new_order})
                all_changes.append((row.id, row.order, new_order))
        ties = [
            {"order": old, "games": [{"game_id": r.id, "name": r.name, "new": n} for r, n in members]}
            for old, members in groups.items() if len(members) > 1
        ]
        locations.append({
            "location_id": location_id,
            "path": [p["name"] for p in path_for(location_id)],
            "games": len(games),
            "changed": len(changes),
            "changes": changes,
            "ties": ties,
        })

    locations.sort(key=lambda loc: loc["path"])
    digest = hashlib.sha256(repr(sorted(all_changes)).encode("utf-8")).hexdigest()[:16]
    return {
        "applied": False,
        "fingerprint": digest,
        "locations": locations,
        "total_games": sum(loc["games"] for loc in locations),
        "total_changed": len(all_changes),
    }


def apply_order_renumbering(session: Session, root_id: int, include_children: bool, fingerprint: str) -> dict:
    """
    Write the renumbering, all-or-nothing. The rows are locked and the plan is recomputed inside the
    transaction; if it no longer matches the previewed `fingerprint` nothing is written.
    """
    ids = _order_location_ids(session, root_id, include_children)
    session.query(Game.id).filter(Game.location_id.in_(ids), Game.order.isnot(None)).order_by(Game.id).with_for_update().all()

    plan = plan_order_renumbering(session, root_id, include_children)
    if plan["fingerprint"] != fingerprint:
        session.rollback()
        raise StaleOrderPlanError("The games changed since the preview. Preview again before applying.")

    updates = [{"id": c["game_id"], "order": c["new"]} for loc in plan["locations"] for c in loc["changes"]]
    try:
        if updates:
            session.execute(update(Game), updates)
        session.commit()
    except Exception:
        session.rollback()
        raise
    plan["applied"] = True
    return plan
