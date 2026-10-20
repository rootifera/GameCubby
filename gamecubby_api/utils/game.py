import asyncio
import logging
import time
from sqlalchemy.orm import Session
from .db_tools import with_db
from .formatting import format_igdb_game
from .location import get_location_path, get_default_location_id
from .mode import upsert_mode
from ..models import game_tags, game_platforms
from ..models.location import Location
from ..schemas.game import GamePreview, PlatformPreview
from ..utils.external import fetch_igdb_game, fetch_igdb_collection
from ..utils.platform import upsert_platform
from ..utils.collection import create_collection
from ..models.game import Game
from ..models.tag import Tag
from ..models.collection import Collection
from ..models.mode import Mode
from ..models.platform import Platform
from ..models.genre import Genre
from ..utils.igdb_tag import upsert_igdb_tags
from sqlalchemy.orm import selectinload
from sqlalchemy import func, or_
from ..models.playerperspective import PlayerPerspective
from ..models.company import Company
from ..models.game_company import GameCompany
from ..models.wishlist import WishlistItem
from ..models.storage import GameFile
from ..utils import storage as storage_mod
from ..utils.file_moves import FileConflictError, FileMovePlan
from ..utils.storage import (
    _cover_s3_key_for,
    _s3_bucket,
    _s3_client,
    _s3_object_exists,
    _s3_uri,
    configured_storage_backend,
)
from ..utils.external import get_igdb_token, _get_igdb_credentials, _post_with_retry
from typing import List, Optional, cast, Dict, Tuple, Union
import asyncio
import os
from pathlib import Path
from contextlib import contextmanager


@contextmanager
def _transaction(session: Session):
    """Use a transaction or savepoint when a caller has already read from the session."""
    if session.in_transaction():
        with session.begin_nested():
            yield
    else:
        with session.begin():
            yield


def get_game(session: Session, game_id: int) -> Optional[Game]:
    game = (
        session.query(Game)
        .options(
            selectinload(Game.platforms),
            selectinload(Game.tags),
            selectinload(Game.collection)
        )
        .filter_by(id=game_id)
        .first()
    )

    if game:
        game.location_path = [
            {"id": str(loc["id"]), "name": loc["name"]}
            for loc in get_location_path(session, game.id)
        ]

    return game


def list_games(session: Session) -> List[Game]:
    games = (
        session.query(Game)
        .options(
            selectinload(Game.platforms),
            selectinload(Game.tags),
            selectinload(Game.collection)
        )
        .all()
    )

    location_ids = set()
    for game in games:
        if game.location_id:
            current_id = game.location_id
            while current_id:
                location_ids.add(current_id)
                loc = session.query(Location.parent_id).filter_by(id=current_id).first()
                current_id = loc[0] if loc else None

    locations = (
        session.query(Location)
        .filter(Location.id.in_(location_ids))
        .all()
    ) if location_ids else []

    loc_dict = {loc.id: loc for loc in locations}

    for game in games:
        game.location_path = []
        current_id = game.location_id

        while current_id in loc_dict:
            loc = loc_dict[current_id]
            game.location_path.insert(0, {
                "id": str(loc.id),
                "name": loc.name
            })
            current_id = loc.parent_id

    return games


def _local_game_ref(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


def _games_sharing_ref(session: Session, ref: str, exclude_game_id: int) -> List[Game]:
    """
    Other games that use the same file reference (same IGDB id, or a custom game whose name
    reduces to the same text). They share one file folder: copies of the same game share
    their images and downloads (patches, manuals, ...).
    """
    found: Dict[int, Game] = {}
    if ref.isdigit():
        for g in session.query(Game).filter(Game.igdb_id == int(ref), Game.id != exclude_game_id):
            found[g.id] = g
    for g in session.query(Game).filter(or_(Game.igdb_id.is_(None), Game.igdb_id == 0), Game.id != exclude_game_id):
        if _local_game_ref(g.name) == ref:
            found[g.id] = g
    return list(found.values())


def _other_games_share_ref(session: Session, ref: str, exclude_game_id: int) -> bool:
    """True if another game uses the same file reference (so its folder must not be moved/removed)."""
    return bool(_games_sharing_ref(session, ref, exclude_game_id))


def _plan_s3_cover_copy(session: Session, plan: FileMovePlan, game: Game, old_key: str, new_key: str,
                        delete_old: bool) -> None:
    """Carry a game's cached cover to its new S3 key (the cover key embeds the game ref)."""
    if not game.cover_cached or configured_storage_backend(session) != "s3":
        return
    client, bucket = _s3_client(session), _s3_bucket(session)
    present = _s3_object_exists(client, bucket, old_key)
    if present is None:
        raise RuntimeError("Could not verify the cached cover in S3; nothing was changed. Try again.")
    if not present:
        return  # the cover was already missing; the cover sync deals with that
    if _s3_object_exists(client, bucket, new_key) is not False:
        raise FileConflictError("Another game already has a cover stored at the new location; nothing was changed.")
    plan.copy_s3(client, bucket, old_key, new_key)
    if delete_old:
        plan.delete_s3_after_commit(client, bucket, old_key)


def _move_local_game_files_for_rename(session: Session, plan: FileMovePlan, game: Game,
                                      old_ref: str, new_ref: str) -> None:
    """
    A custom game was renamed: move its upload folder to the new name's folder and re-point
    its file records. The folder move is recorded in `plan` so the caller can undo it if the
    commit fails. Raises FileConflictError (nothing changed) if the new name's folder is taken.
    """
    if not old_ref or not new_ref or old_ref == new_ref:
        return
    if _other_games_share_ref(session, old_ref, game.id):
        # The files belong to the other game(s) that still use this ref; they stay put.
        return

    old_dir = storage_mod.UPLOADS_DIR / "local" / old_ref
    new_dir = storage_mod.UPLOADS_DIR / "local" / new_ref
    moved_dir = False
    if old_dir.exists():
        if new_dir.exists():
            raise FileConflictError(
                f"Another game already stores files under '{new_ref}'. "
                "Choose a different name, or move those files first; nothing was changed."
            )
        plan.move_dir(old_dir, new_dir)
        moved_dir = True

    old_prefix = str(old_dir)
    new_prefix = str(new_dir)
    for file_record in session.query(GameFile).filter(GameFile.game == old_ref).all():
        file_record.game = new_ref
        path = file_record.path or ""
        if moved_dir and (path == old_prefix or path.startswith(old_prefix + os.sep)):
            file_record.path = new_prefix + path[len(old_prefix):]

    _plan_s3_cover_copy(
        session, plan, game,
        _cover_s3_key_for(session, "local", old_ref), _cover_s3_key_for(session, "local", new_ref),
        delete_old=True,
    )


def _convert_game_file_refs_to_custom(session: Session, plan: FileMovePlan, game: Game,
                                      old_ref: str, new_ref: str) -> None:
    """
    Move an IGDB game's files to the custom-game layout.

    Everything undoable happens before the commit (folder rename, S3 *copies*); old S3
    objects are only deleted afterwards (`plan.finish()`), so a failure never leaves records
    pointing at deleted files. If other games still share the IGDB ref, their files are left
    alone: the folder/objects are copied and the file records duplicated instead of moved.
    Raises FileConflictError (nothing changed) if a destination is already taken.
    """
    if not old_ref or not new_ref or old_ref == new_ref:
        return

    shared = _other_games_share_ref(session, old_ref, game.id)

    old_dir = storage_mod.UPLOADS_DIR / "igdb" / old_ref
    new_dir = storage_mod.UPLOADS_DIR / "local" / new_ref
    local_relocated = False
    if old_dir.exists():
        if new_dir.exists():
            raise FileConflictError(
                f"Another game already stores files under '{new_ref}'. "
                "Rename this game first; nothing was changed."
            )
        (plan.copy_dir if shared else plan.move_dir)(old_dir, new_dir)
        local_relocated = True

    old_prefix = str(old_dir)
    new_prefix = str(new_dir)
    s3_client = None
    s3_bucket = None

    for file_record in session.query(GameFile).filter(GameFile.game == old_ref).all():
        new_path = file_record.path
        new_key = file_record.object_key

        if (file_record.storage_backend or "local") == "s3":
            old_key = file_record.object_key
            if not old_key and (file_record.path or "").startswith("s3://"):
                old_key = (file_record.path or "").split("/", 3)[3]
            parts = old_key.split("/") if old_key else []
            uploads_idx = parts.index("uploads") if "uploads" in parts else -1
            if uploads_idx >= 0 and len(parts) > uploads_idx + 4 and parts[uploads_idx + 1] == "igdb":
                new_parts = parts[:]
                new_parts[uploads_idx + 1] = "local"
                new_parts[uploads_idx + 2] = new_ref
                new_key = "/".join(new_parts)
                if s3_client is None:
                    s3_client, s3_bucket = _s3_client(session), _s3_bucket(session)
                if _s3_object_exists(s3_client, s3_bucket, new_key) is not False:
                    raise FileConflictError(
                        f"'{new_key}' already exists; converting would overwrite it. Nothing was changed."
                    )
                plan.copy_s3(s3_client, s3_bucket, old_key, new_key)
                if not shared:
                    plan.delete_s3_after_commit(s3_client, s3_bucket, old_key)
                new_path = _s3_uri(s3_bucket, new_key)
            elif shared:
                continue  # can't derive a destination for this object; leave the shared record alone
        else:
            path = file_record.path or ""
            if local_relocated and (path == old_prefix or path.startswith(old_prefix + os.sep)):
                new_path = new_prefix + path[len(old_prefix):]
            elif shared:
                continue  # file isn't under the folder we copied; leave the shared record alone

        if shared:
            # Others still reference the original record/file: give this game its own copy.
            session.add(GameFile(
                game=new_ref, label=file_record.label, category=file_record.category,
                path=new_path, storage_backend=file_record.storage_backend,
                object_key=new_key if (file_record.storage_backend or "local") == "s3" else None,
                size=file_record.size, content_type=file_record.content_type,
            ))
        else:
            file_record.game = new_ref
            file_record.path = new_path
            if (file_record.storage_backend or "local") == "s3":
                file_record.object_key = new_key

    _plan_s3_cover_copy(
        session, plan, game,
        _cover_s3_key_for(session, "igdb", old_ref), _cover_s3_key_for(session, "local", new_ref),
        delete_old=not shared,
    )


def convert_igdb_game_to_custom(session: Session, game_id: int) -> Optional[Game]:
    game = session.query(Game).filter_by(id=game_id).first()
    if not game:
        return None
    if not game.igdb_id:
        return game

    old_ref = str(game.igdb_id)
    new_ref = _local_game_ref(game.name)

    plan = FileMovePlan()
    try:
        _convert_game_file_refs_to_custom(session, plan, game, old_ref, new_ref)
        game.igdb_id = 0
        game.updated_at = None
        session.commit()
    except Exception:
        session.rollback()
        plan.rollback()  # put files back / drop the copies: they must match the (rolled back) database
        raise
    plan.finish()  # only now remove the old S3 objects
    session.refresh(game)
    return game


def create_game(session: Session, game_data: dict, *, commit: bool = True) -> Game:
    if game_data.get("location_id") in (None, 0):
        game_data["location_id"] = get_default_location_id(session)

    mode_ids = game_data.pop("mode_ids", [])
    platform_ids = game_data.pop("platform_ids", [])
    genre_ids = game_data.pop("genre_ids", [])
    perspective_ids = game_data.pop("player_perspective_ids", [])
    tag_inputs = game_data.pop("tag_ids", [])  # can be IDs or names
    collection_id = game_data.pop("collection_id", None)
    company_ids = game_data.pop("company_ids", [])

    game_data["igdb_id"] = 0
    game = Game(**game_data)

    if collection_id:
        collection = session.query(Collection).filter_by(id=collection_id).first()
        if collection:
            game.collection = collection

    session.add(game)

    if mode_ids:
        game.modes = session.query(Mode).filter(Mode.id.in_(mode_ids)).all()
    if platform_ids:
        game.platforms = session.query(Platform).filter(Platform.id.in_(platform_ids)).all()
    if genre_ids:
        game.genres = session.query(Genre).filter(Genre.id.in_(genre_ids)).all()
    if perspective_ids:
        game.playerperspectives = session.query(PlayerPerspective).filter(
            PlayerPerspective.id.in_(perspective_ids)).all()

    # Tag handling (create on the fly if needed) + de-dup
    if tag_inputs:
        tags_by_id: dict[int, Tag] = {}
        for t in tag_inputs:
            tag_obj: Optional[Tag] = None
            if isinstance(t, int) or (isinstance(t, str) and t.isdigit()):
                tag_obj = session.query(Tag).filter_by(id=int(t)).first()
            elif isinstance(t, str):
                tag_name = t.strip()
                if not tag_name:
                    continue
                tag_obj = session.query(Tag).filter(
                    func.lower(Tag.name) == tag_name.lower()
                ).first()
                if not tag_obj:
                    tag_obj = Tag(name=tag_name)
                    session.add(tag_obj)
                    session.flush()  # get ID without committing yet
            if tag_obj:
                tags_by_id[tag_obj.id] = tag_obj
        game.tags = list(tags_by_id.values())

    if company_ids:
        companies = session.query(Company).filter(Company.id.in_(company_ids)).all()
        game.companies = [GameCompany(company=c) for c in companies]

    if commit:
        session.commit()
        session.refresh(game)
    else:
        session.flush()
    return game


def update_game(session: Session, game_id: int, update_data: dict) -> Optional[Game]:
    game = session.query(Game).filter_by(id=game_id).first()
    if not game:
        return None

    old_local_ref = _local_game_ref(game.name) if game.igdb_id == 0 else None

    if game.igdb_id != 0:
        allowed_fields = {"location_id", "order", "condition", "tag_ids", "platform_ids"}
        non_null_keys = {k for k, v in update_data.items() if v is not None}
        if not non_null_keys.issubset(allowed_fields):
            raise ValueError("Cannot update IGDB-sourced games except condition/location/order/tags/platforms")

    update_data.pop("igdb_id", None)

    if "location_id" in update_data and update_data["location_id"] in (None, 0):
        update_data["location_id"] = get_default_location_id(session)

    mode_ids = update_data.pop("mode_ids", None)
    if mode_ids is not None:
        game.modes = session.query(Mode).filter(Mode.id.in_(mode_ids)).all()

    platform_ids = update_data.pop("platform_ids", None)
    if platform_ids is not None:
        game.platforms = session.query(Platform).filter(Platform.id.in_(platform_ids)).all()

    genre_ids = update_data.pop("genre_ids", None)
    if genre_ids is not None:
        game.genres = session.query(Genre).filter(Genre.id.in_(genre_ids)).all()

    perspective_ids = update_data.pop("player_perspective_ids", None)
    if perspective_ids is not None:
        game.playerperspectives = session.query(PlayerPerspective).filter(
            PlayerPerspective.id.in_(perspective_ids)
        ).all()

    tag_ids_or_names = update_data.pop("tag_ids", None)
    if tag_ids_or_names is not None:
        tags_by_id: dict[int, Tag] = {}
        for tag_item in tag_ids_or_names:
            tag_obj: Optional[Tag] = None
            if isinstance(tag_item, int) or (isinstance(tag_item, str) and tag_item.isdigit()):
                tag_obj = session.query(Tag).filter_by(id=int(tag_item)).first()
            elif isinstance(tag_item, str):
                tag_name = tag_item.strip()
                if not tag_name:
                    continue
                tag_obj = session.query(Tag).filter(
                    func.lower(Tag.name) == tag_name.lower()
                ).first()
                if not tag_obj:
                    tag_obj = Tag(name=tag_name)
                    session.add(tag_obj)
                    session.flush()
            if tag_obj:
                tags_by_id[tag_obj.id] = tag_obj
        game.tags = list(tags_by_id.values())

    collection_id = update_data.pop("collection_id", None)
    if collection_id is not None:
        game.collection = session.query(Collection).filter_by(id=collection_id).first()

    company_ids = update_data.pop("company_ids", None)
    if company_ids is not None:
        existing_by_cid: dict[int, GameCompany] = {gc.company_id: gc for gc in game.companies}
        companies = session.query(Company).filter(Company.id.in_(company_ids)).all()
        new_links: list[GameCompany] = []
        for c in companies:
            if c.id in existing_by_cid:
                new_links.append(existing_by_cid[c.id])  # keep existing flags
            else:
                new_links.append(
                    GameCompany(
                        company=c,
                        developer=False,
                        publisher=False,
                        porting=False,
                        supporting=False,
                    )
                )
        game.companies = new_links

    for key, value in update_data.items():
        if value is not None:
            setattr(game, key, value)

    plan = FileMovePlan()
    try:
        if old_local_ref and "name" in update_data and update_data["name"]:
            new_local_ref = _local_game_ref(str(update_data["name"]))
            _move_local_game_files_for_rename(session, plan, game, old_local_ref, new_local_ref)
        session.commit()
    except Exception:
        session.rollback()
        plan.rollback()  # the folder must go back if the database change didn't happen
        raise
    plan.finish()
    session.refresh(game)

    for link in getattr(game, "companies", []) or []:
        link.developer = bool(link.developer)
        link.publisher = bool(link.publisher)
        link.porting = bool(link.porting)
        link.supporting = bool(link.supporting)

    return game




def get_delete_impact(session: Session, game_id: int) -> Optional[dict]:
    """
    What "also delete files" would remove for this game: its registered files, its cached
    cover, and which other copies share them. Read-only; used to inform the admin before
    they choose.
    """
    game = session.query(Game).filter_by(id=game_id).first()
    if not game:
        return None
    ref = storage_mod.get_game_ref(game)
    records = session.query(GameFile).filter(GameFile.game == ref).all() if ref else []
    others = _games_sharing_ref(session, ref, game.id) if ref else []
    return {
        "game_id": game.id,
        "can_delete_files": bool(ref),
        "file_count": len(records),
        "total_bytes": sum(int(r.size or 0) for r in records),
        "has_cover": bool(game.cover_cached),
        "other_copies": [{"id": g.id, "name": g.name} for g in others],
    }


def delete_game(session: Session, game_id: int, *, delete_files: bool = False) -> bool:
    """
    Delete a game by its ID. Returns True if deleted, False if not found.

    By default this NEVER deletes stored files, file records or covers, on purpose: a library
    can hold several copies of the same game (same IGDB id, or the same custom name) and they
    share one set of images and downloads (patches, manuals, ...). Removing one damaged copy
    must not take those away from the others -- and re-adding a game re-attaches its files.

    `delete_files=True` is the admin's explicit opt-in to remove them anyway: every file record,
    the stored files (local folder / S3 objects) and the cached cover for this game's ref --
    which means for ALL copies, so the other copies' cached-cover flag is cleared too.
    The database changes commit first; the stored files are removed only afterwards.
    """
    game = session.query(Game).filter_by(id=game_id).first()
    if not game:
        return False

    plan = FileMovePlan()
    if delete_files:
        ref = storage_mod.get_game_ref(game)
        if not ref:
            # An empty ref would resolve to the whole uploads folder: refuse outright.
            raise ValueError("Can't determine this game's file location, so its files can't be deleted.")
        group = "igdb" if game.igdb_id else "local"
        records = session.query(GameFile).filter(GameFile.game == ref).all()

        local_dir = storage_mod.UPLOADS_DIR / group / ref
        uploads_root = storage_mod.UPLOADS_DIR.resolve()
        if Path(ref).name != ref or uploads_root not in local_dir.resolve().parents:
            raise ValueError("Refusing to delete outside the uploads folder.")

        # Everything that needs the DB session (S3 settings) is resolved before the commit.
        s3_client = s3_bucket = s3_prefix = None
        record_keys = {r.object_key for r in records if (r.storage_backend or "local") == "s3" and r.object_key}
        if record_keys or configured_storage_backend(session) == "s3":
            s3_client, s3_bucket = _s3_client(session), _s3_bucket(session)
            s3_prefix = storage_mod._s3_game_prefix(session, group, ref)

        for other in _games_sharing_ref(session, ref, game.id):
            other.cover_cached = False  # their cover file is about to be removed with the rest
        session.query(GameFile).filter(GameFile.game == ref).delete(synchronize_session=False)

        plan.delete_dir_after_commit(local_dir)
        if s3_client is not None:
            plan.after_commit(lambda: _delete_s3_files(s3_client, s3_bucket, s3_prefix, record_keys))

    try:
        # Detach any wishlist resolutions that reference this game before deleting,
        # since the FK has no ON DELETE action defined.
        session.query(WishlistItem).filter_by(library_game_id=game_id).update(
            {"library_game_id": None}, synchronize_session=False
        )
        session.delete(game)
        session.commit()
    except Exception:
        session.rollback()
        plan.rollback()
        raise
    plan.finish()
    return True


def _delete_s3_files(client, bucket: str, prefix: str, extra_keys: set) -> None:
    """Remove every object under a game's S3 folder, plus any registered key stored elsewhere."""
    keys = set(extra_keys)
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys.update(obj["Key"] for obj in page.get("Contents", []))
    batch = sorted(keys)
    for i in range(0, len(batch), 1000):
        client.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in batch[i:i + 1000]], "Quiet": True})


def list_games_by_tag(session: Session, tag_id: int) -> List[Game]:
    """
    Return all games associated with a given tag ID.
    """
    return (
        session.query(Game)
        .join(game_tags, Game.id == game_tags.c.game_id)
        .filter(game_tags.c.tag_id == tag_id)
        .order_by(Game.name)
        .all()
    )


def list_games_by_platform(session: Session, platform_id: int) -> List[Game]:
    """
    Return all games associated with a given platform ID.
    """
    return (
        session.query(Game)
        .join(game_platforms, Game.id == game_platforms.c.game_id)
        .filter(game_platforms.c.platform_id == platform_id)
        .order_by(Game.name)
        .all()
    )


def list_games_by_location(session: Session, location_id: int) -> List[Game]:
    """
    Return all games stored at the specified location.
    """
    games = (
        session.query(Game)
        .filter(Game.location_id == location_id)
        .order_by(Game.name)
        .all()
    )
    return cast(List[Game], games)


def upsert_collection(session: Session, collection_obj: Dict) -> Collection:
    """
    Finds an existing collection by IGDB ID or name, or creates a new one.
    """
    existing = session.query(Collection).filter_by(igdb_id=collection_obj["id"]).first()
    if not existing:
        existing = session.query(Collection).filter_by(name=collection_obj["name"]).first()
    if existing:
        return existing

    return create_collection(session, {
        "igdb_id": collection_obj["id"],
        "name": collection_obj["name"]
    })


async def add_game_from_igdb(
    session: Session,
    igdb_id: int,
    platform_ids: list[int],
    location_id: Optional[int] = None,
    tag_ids: list[Union[int, str]] = [],
    condition: Optional[int] = None,
    order: Optional[int] = None,
    *,
    commit: bool = True,
) -> Optional[Game]:
    raw = await fetch_igdb_game(igdb_id)
    if not raw:
        return None

    game_data = format_igdb_game(raw, session)
    name = game_data["name"]
    summary = game_data["summary"]
    release_date = game_data["release_date"]
    cover_url = game_data["cover_url"]
    rating = int(raw["rating"]) if raw.get("rating") else None
    updated_at = raw.get("updated_at")

    igdb_tag_ids = raw.get("tags", [])
    tags = await upsert_igdb_tags(session, igdb_tag_ids, commit=commit)

    involved_company_ids = raw.get("involved_companies", [])
    involved_company_data = []
    company_name_map = {}

    if involved_company_ids:
        client_id, _ = _get_igdb_credentials(session)
        token = await get_igdb_token()
        headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}"
        }

        resp = await _post_with_retry(
            "https://api.igdb.com/v4/involved_companies",
            headers=headers,
            data=f"fields company,developer,publisher,porting,supporting; where id = ({','.join(map(str, involved_company_ids))});",
        )
        involved_company_data = resp.json()

        company_ids = {c["company"] for c in involved_company_data if "company" in c}
        if company_ids:
            resp = await _post_with_retry(
                "https://api.igdb.com/v4/companies",
                headers=headers,
                data=f"fields id,name; where id = ({','.join(map(str, company_ids))});",
            )
            for c in resp.json():
                company_name_map[c["id"]] = c["name"]

    collection_id = None
    collection_list = await fetch_igdb_collection(igdb_id)
    if collection_list:
        data = collection_list[0]
        collection = session.query(Collection).filter_by(igdb_id=data["id"]).first()
        if not collection:
            collection = Collection(igdb_id=data["id"], name=data["name"])
            session.add(collection)
            if commit:
                session.commit()
                session.refresh(collection)
            else:
                session.flush()
        collection_id = collection.id

    final_location_id = location_id if location_id not in (None, 0) else get_default_location_id(session)

    game = Game(
        igdb_id=igdb_id,
        name=name,
        summary=summary,
        release_date=release_date,
        cover_url=cover_url,
        location_id=final_location_id,
        condition=condition,
        order=order,
        collection_id=collection_id,
        rating=rating,
        updated_at=updated_at,
    )
    session.add(game)

    for mode_item in game_data.get("game_modes", []):
        mode_id = mode_item["id"] if isinstance(mode_item, dict) else mode_item
        mode_name = mode_item.get("name") if isinstance(mode_item, dict) else ""
        mode = session.query(Mode).filter_by(id=mode_id).first()
        if not mode:
            mode = upsert_mode(session, mode_id, mode_name or "", commit=commit)
        if mode and mode not in game.modes:
            game.modes.append(mode)

    for genre_item in game_data.get("genres", []):
        genre_id = genre_item["id"] if isinstance(genre_item, dict) else genre_item
        genre = session.query(Genre).filter_by(id=genre_id).first()
        if genre and genre not in game.genres:
            game.genres.append(genre)

    igdb_platforms = {p["id"]: p for p in game_data.get("platforms", [])}
    for platform_id in platform_ids:
        platform = session.query(Platform).filter_by(id=platform_id).first()
        if not platform and platform_id in igdb_platforms:
            platform = upsert_platform(session, igdb_platforms[platform_id], commit=commit)
        if platform and platform not in game.platforms:
            game.platforms.append(platform)

    # Updated tag handling: accept IDs or names + de-dup
    tags_by_id: dict[int, Tag] = {}
    for tag_val in tag_ids:
        tag_obj: Optional[Tag] = None
        if isinstance(tag_val, int) or (isinstance(tag_val, str) and tag_val.isdigit()):
            tag_obj = session.query(Tag).filter_by(id=int(tag_val)).first()
        elif isinstance(tag_val, str):
            tag_name = tag_val.strip()
            if tag_name:
                tag_obj = session.query(Tag).filter(
                    func.lower(Tag.name) == tag_name.lower()
                ).first()
                if not tag_obj:
                    tag_obj = Tag(name=tag_name)
                    session.add(tag_obj)
                    session.flush()
        if tag_obj:
            tags_by_id[tag_obj.id] = tag_obj
    if tags_by_id:
        game.tags.extend([t for t in tags_by_id.values() if t not in game.tags])

    for p_id in raw.get("player_perspectives", []):
        perspective = session.query(PlayerPerspective).filter_by(id=p_id).first()
        if perspective and perspective not in game.playerperspectives:
            game.playerperspectives.append(perspective)

    for tag in tags:
        if tag not in game.igdb_tags:
            game.igdb_tags.append(tag)

    merged_companies: dict[int, dict[str, bool]] = {}
    for ic in involved_company_data:
        cid = ic.get("company")
        if cid is None:
            continue
        entry = merged_companies.setdefault(
            cid,
            {"developer": False, "publisher": False, "porting": False, "supporting": False},
        )
        for k in ("developer", "publisher", "porting", "supporting"):
            if ic.get(k, False):
                entry[k] = True

    for cid, flags in merged_companies.items():
        name = company_name_map.get(cid, "Unknown")

        company = session.query(Company).filter_by(id=cid).first()
        if not company:
            company = Company(id=cid, name=name)
            session.add(company)
            session.flush()

        link = GameCompany(
            company_id=cid,
            developer=flags["developer"],
            publisher=flags["publisher"],
            porting=flags["porting"],
            supporting=flags["supporting"],
        )
        game.companies.append(link)

    if commit:
        session.commit()
        session.refresh(game)
    else:
        session.flush()
    return game


def create_game_and_resolve_wishlist(session: Session, game_data: dict, wishlist_id: int) -> Game:
    """Create a manual game and resolve its active Wishlist item in one transaction."""
    from .wishlist import resolve_wishlist_item

    with _transaction(session):
        game = create_game(session, game_data, commit=False)
        resolve_wishlist_item(session, wishlist_id, game.id, commit=False)
    session.refresh(game)
    return game


async def add_igdb_game_and_resolve_wishlist(
    session: Session,
    *,
    wishlist_id: int,
    igdb_id: int,
    platform_ids: list[int],
    location_id: Optional[int] = None,
    tag_ids: list[Union[int, str]] | None = None,
    condition: Optional[int] = None,
    order: Optional[int] = None,
) -> Optional[Game]:
    """Create an IGDB game and resolve its active Wishlist item in one transaction."""
    from .wishlist import resolve_wishlist_item

    with _transaction(session):
        game = await add_game_from_igdb(
            session,
            igdb_id=igdb_id,
            platform_ids=platform_ids,
            location_id=location_id,
            tag_ids=tag_ids or [],
            condition=condition,
            order=order,
            commit=False,
        )
        if not game:
            return None
        resolve_wishlist_item(session, wishlist_id, game.id, commit=False)
    session.refresh(game)
    return game


async def purchase_wishlist_item(
    session: Session,
    *,
    wishlist_id: int,
    location_id: Optional[int] = None,
    condition: Optional[int] = None,
    order: Optional[int] = None,
    tag_ids: list[Union[int, str]] | None = None,
) -> Game:
    """Use the normal creation services to purchase and resolve a Wishlist item atomically."""
    from .wishlist import active_wishlist_item_for_update, resolve_wishlist_item

    with _transaction(session):
        item = active_wishlist_item_for_update(session, wishlist_id)
        platform_ids = [platform.id for platform in item.platforms]
        if item.igdb_id:
            game = await add_game_from_igdb(
                session,
                igdb_id=item.igdb_id,
                platform_ids=platform_ids,
                location_id=location_id,
                tag_ids=tag_ids or [],
                condition=condition,
                order=order,
                commit=False,
            )
            if not game:
                raise LookupError("Game not found on IGDB")
        else:
            game = create_game(session, {
                "name": item.name,
                "release_date": item.release_year,
                "cover_url": item.cover_url,
                "platform_ids": platform_ids,
                "location_id": location_id,
                "condition": condition,
                "order": order,
                "tag_ids": tag_ids or [],
            }, commit=False)
        resolve_wishlist_item(session, wishlist_id, game.id, commit=False)
    session.refresh(game)
    return game


# The status check is public (the game page calls it for every visitor) and each live
# check is an IGDB request, so results are cached per process. The key includes the
# game's own `updated_at`: an admin refreshing a game's metadata changes it, which
# invalidates that game's entry immediately.
_STATUS_TTL_OK = 6 * 3600     # a definite answer from IGDB
_STATUS_TTL_FAILED = 60       # IGDB unreachable / no timestamp: retry soon, but not on every page view
_STATUS_CACHE_MAX = 4096
_status_cache: "dict[tuple, tuple[float, dict]]" = {}
_status_inflight: "dict[tuple, asyncio.Future]" = {}


def _status_cache_get(key: tuple) -> Optional[dict]:
    entry = _status_cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    _status_cache.pop(key, None)
    return None


def _status_cache_put(key: tuple, value: dict) -> None:
    if len(_status_cache) >= _STATUS_CACHE_MAX:
        now = time.monotonic()
        for k in [k for k, (exp, _) in _status_cache.items() if exp <= now] or [next(iter(_status_cache))]:
            _status_cache.pop(k, None)
    ttl = _STATUS_TTL_OK if value.get("checked") else _STATUS_TTL_FAILED
    _status_cache[key] = (time.monotonic() + ttl, value)


def lookup_metadata_status_inputs(game_id: int) -> Optional[dict]:
    """
    The only database work the status check needs, done in its own short session that is
    closed before IGDB is contacted. (Holding a request-scoped session across the IGDB call
    kept a connection checked out, idle, for the whole network round trip.)
    """
    with with_db() as db:
        row = db.query(Game.igdb_id, Game.updated_at).filter(Game.id == game_id).first()
    if row is None:
        return None
    return {"igdb_id": row.igdb_id, "local_updated_at": row.updated_at}


async def check_game_metadata_status(session: Session, game_id: int) -> Optional[dict]:
    """
    Compare a game's local updated_at against IGDB's current value.
    Returns None if the game does not exist (caller should raise 404).
    Returns a dict describing update availability without modifying any data.
    Results are cached (see above) so page views can't turn into a stream of IGDB requests.
    """
    row = session.query(Game.igdb_id, Game.updated_at).filter(Game.id == game_id).first()
    if row is None:
        return None
    return await check_metadata_status_for(game_id, row.igdb_id, row.updated_at)


async def check_metadata_status_for(game_id: int, igdb_id: Optional[int], local_updated_at: Optional[int]) -> dict:
    """The status check itself: needs no database access."""
    base = {"game_id": game_id, "igdb_id": igdb_id or None}

    if not igdb_id:
        return {**base, "igdb_id": None, "checked": True, "update_available": False,
                "message": "This game is not linked to IGDB."}

    key = (game_id, igdb_id, local_updated_at)
    cached = _status_cache_get(key)
    if cached is not None:
        return cached

    # Concurrent requests for the same game share one IGDB call.
    inflight = _status_inflight.get(key)
    if inflight is not None:
        return await asyncio.shield(inflight)

    future: asyncio.Future = asyncio.get_running_loop().create_future()
    _status_inflight[key] = future
    try:
        try:
            raw = await fetch_igdb_game(igdb_id)
        except Exception as exc:  # IGDB down / credentials missing: remember briefly, don't retry per page view
            logging.getLogger(__name__).warning("IGDB status check failed for game %s: %s", game_id, exc)
            raw = None
        igdb_updated_at = raw.get("updated_at") if raw else None
        if not raw:
            result = {**base, "checked": False, "update_available": False,
                      "local_updated_at": local_updated_at,
                      "message": "Could not reach IGDB to check for updates."}
        elif igdb_updated_at is None:
            result = {**base, "checked": False, "update_available": False,
                      "local_updated_at": local_updated_at,
                      "message": "IGDB did not return an update timestamp."}
        else:
            update_available = local_updated_at != igdb_updated_at
            result = {
                **base,
                "checked": True,
                "update_available": update_available,
                "local_updated_at": local_updated_at,
                "igdb_updated_at": igdb_updated_at,
                "message": "Metadata update available from IGDB." if update_available else "Metadata is already current.",
            }
        _status_cache_put(key, result)
        future.set_result(result)
        return result
    except BaseException as exc:
        future.set_exception(exc)
        future.exception()  # mark retrieved so asyncio doesn't warn when nobody else awaited it
        raise
    finally:
        _status_inflight.pop(key, None)


async def refresh_game_metadata(session: Session, game_id: int, *, force: bool = False) -> Tuple[Optional[Game], bool, str]:
    """
    Refresh a game's metadata from IGDB if IGDB's updated_at is newer.
    With `force=True` the metadata is re-applied even when the timestamps match.
    Returns: (game, was_updated (bool), message)

    NOTE: This does NOT modify platforms. We preserve the user's selected platforms.
    """
    game = session.query(Game).filter_by(id=game_id).first()
    if not game:
        return None, False, "Game not found."

    if not game.igdb_id or game.igdb_id == 0:
        return game, False, "Game has no IGDB ID (not an IGDB-backed game)."

    raw = await fetch_igdb_game(game.igdb_id)
    if not raw:
        return game, False, "Could not fetch IGDB game."

    igdb_updated_at = raw.get("updated_at")
    if igdb_updated_at is None:
        return game, False, "IGDB game missing updated_at."

    if game.updated_at == igdb_updated_at and not force:
        return game, False, "Already up to date."

    game_data = format_igdb_game(raw, session)
    new_cover_url = game_data["cover_url"]
    if new_cover_url != game.cover_url:
        game.cover_cached = False
    game.name = game_data["name"]
    game.summary = game_data["summary"]
    game.release_date = game_data["release_date"]
    game.cover_url = new_cover_url
    game.rating = int(raw["rating"]) if raw.get("rating") is not None else None
    game.updated_at = igdb_updated_at

    genre_ids = [g["id"] for g in game_data.get("genres", [])]
    if genre_ids:
        game.genres = session.query(Genre).filter(Genre.id.in_(genre_ids)).all()

    mode_ids = [m["id"] for m in game_data.get("game_modes", [])]
    if mode_ids:
        game.modes = session.query(Mode).filter(Mode.id.in_(mode_ids)).all()

    # IMPORTANT: Do not update platforms here.
    # We intentionally skip syncing platforms to preserve the user's owned selection.

    session.commit()
    session.refresh(game)
    return game, True, "Game metadata updated from IGDB."


def refresh_all_games_metadata(session: Session, *, force: bool = False) -> Dict[str, int]:
    """
    Refresh metadata for all IGDB-backed games.
    Returns summary: {updated: int, skipped: int, errors: int}

    Each game is handled on its own: a failure rolls back just that game (a DB error would
    otherwise leave the shared session unusable and fail every game after it), and the
    transaction is ended after every game so the job doesn't hold a pooled connection idle
    through the IGDB calls and pauses (a full run takes about 10 minutes).
    """
    updated, skipped, errors = 0, 0, 0
    game_ids = [row.id for row in session.query(Game.id).filter(Game.igdb_id.isnot(None), Game.igdb_id > 0).all()]
    session.rollback()  # end the read transaction used to collect the ids

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        for game_id in game_ids:
            try:
                async def do_refresh():
                    result = await refresh_game_metadata(session, game_id, force=force)
                    await asyncio.sleep(1.0)
                    return result

                _, did_update, msg = loop.run_until_complete(do_refresh())

                if did_update:
                    updated += 1
                elif isinstance(msg, str) and "up to date" in msg.lower():
                    skipped += 1
                else:
                    errors += 1
            except Exception as e:
                print(f"Error refreshing game {game_id}: {e}")
                errors += 1
            finally:
                session.rollback()  # discard anything uncommitted after a failure; end the transaction either way
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    print(f"Batch refresh: updated={updated}, skipped={skipped}, errors={errors}")
    return {"updated": updated, "skipped": skipped, "errors": errors}


def force_refresh_metadata(session: Session) -> Dict[str, int]:
    """
    Re-apply IGDB metadata to every IGDB-backed game, even where nothing changed.

    This used to set every game's updated_at to 0 and commit that BEFORE contacting IGDB, to trick
    the "already up to date" check. If IGDB then failed (outage, rate limit, revoked key), every
    game was left flagged "update available" with its real timestamp lost. A `force` flag skips
    the check instead, so a failed run changes nothing.
    """
    return refresh_all_games_metadata(session, force=True)


def list_games_preview(db: Session) -> list[GamePreview]:
    games = db.query(Game).options(selectinload(Game.platforms)).all()
    result = []

    for game in games:
        preview = GamePreview(
            id=game.id,
            igdb_id=game.igdb_id or None,
            name=game.name,
            cover_url=game.cover_url,
            cover_cached=game.cover_cached,
            release_date=game.release_date,
            summary=game.summary,
            rating=game.rating,
            platforms=[
                PlatformPreview(
                    id=platform.id,
                    name=platform.name
                )
                for platform in game.platforms
            ]
        )
        result.append(preview)

    return result
