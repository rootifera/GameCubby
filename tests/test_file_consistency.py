"""
Stored files (local folders, S3 objects) must stay consistent with the database:
nothing is moved/deleted for good until the commit has succeeded, a failed commit puts
everything back, and games that share a file folder never lose files because of a sibling.
"""
import asyncio
import io
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from gamecubby_api.models import Base
from gamecubby_api.models.game import Game
from gamecubby_api.models.storage import FileCategory, GameFile
from gamecubby_api.utils import game as game_utils
from gamecubby_api.utils import storage
from gamecubby_api.utils.file_moves import FileConflictError

CAT = list(FileCategory)[0]


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(storage, "UPLOADS_DIR", root)
    return root


def _file(path: Path, content=b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _record(db, game_ref, path, **kw):
    rec = GameFile(game=game_ref, label="f", path=str(path), category=CAT, storage_backend="local", **kw)
    db.add(rec)
    db.commit()
    return rec


def _fail_commit(db, monkeypatch):
    def boom():
        raise RuntimeError("simulated commit failure")
    monkeypatch.setattr(db, "commit", boom)


# ---------------------------------------------------------------- rename (local)

def test_rename_moves_the_folder_and_repoints_records(db, uploads):
    g = Game(name="Foo Bar", igdb_id=0); db.add(g); db.commit()
    f = _file(uploads / "local" / "foobar" / "rom" / "x.bin")
    rec = _record(db, "foobar", f)

    game_utils.update_game(db, g.id, {"name": "New Name"})

    assert not (uploads / "local" / "foobar").exists()
    moved = uploads / "local" / "newname" / "rom" / "x.bin"
    assert moved.read_bytes() == b"data"
    db.refresh(rec)
    assert rec.game == "newname" and rec.path == str(moved)


def test_rename_with_failed_commit_puts_the_folder_back(db, uploads, monkeypatch):
    g = Game(name="Foo Bar", igdb_id=0); db.add(g); db.commit()
    f = _file(uploads / "local" / "foobar" / "rom" / "x.bin")
    rec = _record(db, "foobar", f)
    _fail_commit(db, monkeypatch)

    with pytest.raises(RuntimeError):
        game_utils.update_game(db, g.id, {"name": "New Name"})

    assert f.read_bytes() == b"data", "files must still be where the (rolled back) database says"
    assert not (uploads / "local" / "newname").exists()
    db.refresh(rec)
    assert rec.game == "foobar" and rec.path == str(f)


def test_rename_onto_an_existing_folder_is_refused_and_changes_nothing(db, uploads):
    g = Game(name="Foo", igdb_id=0); db.add(g); db.commit()
    _file(uploads / "local" / "foo" / "rom" / "a.bin", b"mine")
    _file(uploads / "local" / "bar" / "rom" / "b.bin", b"someone else's")

    with pytest.raises(FileConflictError):
        game_utils.update_game(db, g.id, {"name": "Bar"})

    assert (uploads / "local" / "foo" / "rom" / "a.bin").read_bytes() == b"mine"
    assert (uploads / "local" / "bar" / "rom" / "b.bin").read_bytes() == b"someone else's"


def test_rename_leaves_files_alone_when_another_game_shares_the_folder(db, uploads):
    a = Game(name="Foo", igdb_id=0); b = Game(name="foo!", igdb_id=0)  # both reduce to "foo"
    db.add_all([a, b]); db.commit()
    f = _file(uploads / "local" / "foo" / "rom" / "x.bin")
    rec = _record(db, "foo", f)

    game_utils.update_game(db, a.id, {"name": "Totally Different"})

    assert f.exists(), "the other game still owns this folder"
    db.refresh(rec)
    assert rec.game == "foo" and rec.path == str(f)


# ------------------------------------------------------------ convert (local)

def test_convert_moves_files_to_the_custom_layout(db, uploads):
    g = Game(name="Zelda Clone", igdb_id=77); db.add(g); db.commit()
    f = _file(uploads / "igdb" / "77" / "rom" / "x.bin")
    rec = _record(db, "77", f)

    game_utils.convert_igdb_game_to_custom(db, g.id)

    new = uploads / "local" / "zeldaclone" / "rom" / "x.bin"
    assert new.read_bytes() == b"data" and not (uploads / "igdb" / "77").exists()
    db.refresh(rec)
    assert rec.game == "zeldaclone" and rec.path == str(new) and g.igdb_id == 0


def test_convert_with_failed_commit_restores_everything(db, uploads, monkeypatch):
    g = Game(name="Zelda Clone", igdb_id=77); db.add(g); db.commit()
    f = _file(uploads / "igdb" / "77" / "rom" / "x.bin")
    rec = _record(db, "77", f)
    _fail_commit(db, monkeypatch)

    with pytest.raises(RuntimeError):
        game_utils.convert_igdb_game_to_custom(db, g.id)

    assert f.read_bytes() == b"data" and not (uploads / "local" / "zeldaclone").exists()
    db.refresh(rec); db.refresh(g)
    assert rec.game == "77" and rec.path == str(f) and g.igdb_id == 77


def test_convert_a_duplicate_copies_instead_of_taking_the_files_from_its_twin(db, uploads):
    # Two library entries with the same IGDB id (e.g. one per platform) share one folder.
    mine = Game(name="Zelda Clone", igdb_id=77); twin = Game(name="Zelda Clone (SNES)", igdb_id=77)
    db.add_all([mine, twin]); db.commit()
    f = _file(uploads / "igdb" / "77" / "rom" / "x.bin")
    _record(db, "77", f)

    game_utils.convert_igdb_game_to_custom(db, mine.id)

    assert f.read_bytes() == b"data", "the twin must keep its files"
    copy = uploads / "local" / "zeldaclone" / "rom" / "x.bin"
    assert copy.read_bytes() == b"data"
    refs = sorted(r.game for r in db.query(GameFile).all())
    assert refs == ["77", "zeldaclone"], "original record stays, a new record is added for the converted game"


def test_convert_onto_an_existing_folder_is_refused(db, uploads):
    g = Game(name="Zelda Clone", igdb_id=77); db.add(g); db.commit()
    _file(uploads / "igdb" / "77" / "rom" / "x.bin", b"igdb files")
    _file(uploads / "local" / "zeldaclone" / "rom" / "x.bin", b"another custom game")

    with pytest.raises(FileConflictError):
        game_utils.convert_igdb_game_to_custom(db, g.id)

    assert (uploads / "igdb" / "77" / "rom" / "x.bin").read_bytes() == b"igdb files"
    assert (uploads / "local" / "zeldaclone" / "rom" / "x.bin").read_bytes() == b"another custom game"


# ------------------------------------------------------------------ convert (S3)

class _Err(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self, objects):
        self.objects = dict(objects)
        self.deleted = []

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise _Err("404")
        return {}

    def copy_object(self, Bucket, CopySource, Key):
        self.objects[Key] = self.objects[CopySource["Key"]]

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)
        self.objects.pop(Key, None)


@pytest.fixture
def s3(monkeypatch):
    def install(objects):
        fake = FakeS3(objects)
        monkeypatch.setattr(game_utils, "_s3_client", lambda db, **kw: fake)
        monkeypatch.setattr(game_utils, "_s3_bucket", lambda db: "bucket")
        monkeypatch.setattr(game_utils, "configured_storage_backend", lambda db: "s3")
        monkeypatch.setattr(storage, "_s3_prefix", lambda db: "")
        return fake
    return install


def _s3_record(db, ref, key):
    rec = GameFile(game=ref, label="f", path=f"s3://bucket/{key}", category=CAT, storage_backend="s3", object_key=key)
    db.add(rec)
    db.commit()
    return rec


def test_s3_convert_copies_first_and_deletes_old_objects_only_after_commit(db, uploads, s3):
    g = Game(name="Zelda Clone", igdb_id=77, cover_cached=True); db.add(g); db.commit()
    fake = s3({"uploads/igdb/77/rom/x.bin": b"d", "uploads/igdb/77/metadata/cover.jpg": b"c"})
    rec = _s3_record(db, "77", "uploads/igdb/77/rom/x.bin")

    game_utils.convert_igdb_game_to_custom(db, g.id)

    assert set(fake.objects) == {"uploads/local/zeldaclone/rom/x.bin", "uploads/local/zeldaclone/metadata/cover.jpg"}
    db.refresh(rec)
    assert rec.object_key == "uploads/local/zeldaclone/rom/x.bin" and rec.path.endswith("local/zeldaclone/rom/x.bin")


def test_s3_convert_with_failed_commit_leaves_the_original_objects_untouched(db, uploads, s3, monkeypatch):
    g = Game(name="Zelda Clone", igdb_id=77); db.add(g); db.commit()
    fake = s3({"uploads/igdb/77/rom/x.bin": b"d"})
    rec = _s3_record(db, "77", "uploads/igdb/77/rom/x.bin")
    _fail_commit(db, monkeypatch)

    with pytest.raises(RuntimeError):
        game_utils.convert_igdb_game_to_custom(db, g.id)

    assert set(fake.objects) == {"uploads/igdb/77/rom/x.bin"}, "old object kept, the copy cleaned up"
    assert "uploads/igdb/77/rom/x.bin" not in fake.deleted
    db.refresh(rec)
    assert rec.object_key == "uploads/igdb/77/rom/x.bin"


def test_s3_convert_never_overwrites_another_games_object(db, uploads, s3):
    g = Game(name="Zelda Clone", igdb_id=77); db.add(g); db.commit()
    fake = s3({"uploads/igdb/77/rom/x.bin": b"mine", "uploads/local/zeldaclone/rom/x.bin": b"theirs"})
    _s3_record(db, "77", "uploads/igdb/77/rom/x.bin")

    with pytest.raises(FileConflictError):
        game_utils.convert_igdb_game_to_custom(db, g.id)

    assert fake.objects["uploads/local/zeldaclone/rom/x.bin"] == b"theirs"
    assert fake.objects["uploads/igdb/77/rom/x.bin"] == b"mine" and fake.deleted == []


def test_s3_convert_of_a_duplicate_keeps_the_twins_objects(db, uploads, s3):
    mine = Game(name="Zelda Clone", igdb_id=77); twin = Game(name="Twin", igdb_id=77)
    db.add_all([mine, twin]); db.commit()
    fake = s3({"uploads/igdb/77/rom/x.bin": b"d"})
    _s3_record(db, "77", "uploads/igdb/77/rom/x.bin")

    game_utils.convert_igdb_game_to_custom(db, mine.id)

    assert "uploads/igdb/77/rom/x.bin" in fake.objects and "uploads/local/zeldaclone/rom/x.bin" in fake.objects
    assert fake.deleted == []


def test_s3_rename_carries_a_custom_cover_to_the_new_key(db, uploads, s3):
    g = Game(name="Foo Bar", igdb_id=0, cover_cached=True); db.add(g); db.commit()
    fake = s3({"uploads/local/foobar/metadata/cover.jpg": b"my uploaded cover"})

    game_utils.update_game(db, g.id, {"name": "New Name"})

    assert set(fake.objects) == {"uploads/local/newname/metadata/cover.jpg"}
    assert fake.objects["uploads/local/newname/metadata/cover.jpg"] == b"my uploaded cover"


# ---------------------------------------------------------------- delete a file

def test_delete_file_keeps_the_stored_file_if_the_commit_fails(db, uploads, monkeypatch):
    f = _file(uploads / "local" / "foo" / "rom" / "x.bin")
    rec = _record(db, "foo", f)
    _fail_commit(db, monkeypatch)

    with pytest.raises(Exception):
        asyncio.run(storage.delete_game_file(db, rec.id))

    assert f.exists(), "the file must survive when the database change didn't happen"


def test_delete_file_removes_record_then_file(db, uploads):
    f = _file(uploads / "local" / "foo" / "rom" / "x.bin")
    rec = _record(db, "foo", f)
    rid = rec.id

    asyncio.run(storage.delete_game_file(db, rid))

    assert not f.exists() and db.get(GameFile, rid) is None


def test_delete_s3_file_happens_after_the_commit(db, uploads, monkeypatch):
    fake = FakeS3({"uploads/local/foo/rom/x.bin": b"d"})
    monkeypatch.setattr(storage, "_s3_client", lambda db, **kw: fake)
    monkeypatch.setattr(storage, "_s3_bucket", lambda db: "bucket")
    rec = _s3_record(db, "foo", "uploads/local/foo/rom/x.bin")

    order = []
    real_commit = db.commit
    monkeypatch.setattr(db, "commit", lambda: (order.append("commit"), real_commit())[1])
    original_delete = fake.delete_object
    fake.delete_object = lambda Bucket, Key: (order.append("s3-delete"), original_delete(Bucket, Key))[1]

    asyncio.run(storage.delete_game_file(db, rec.id))
    assert order == ["commit", "s3-delete"]


# ------------------------------------------------------------------- uploads

class _Upload:
    """Minimal UploadFile stand-in; `fail_after` makes the stream die mid-upload."""
    content_type = "application/octet-stream"

    def __init__(self, data: bytes, fail_after: int | None = None):
        self.file = io.BytesIO(data)
        self._fail_after = fail_after
        self._read = 0

    async def read(self, n=-1):
        if self._fail_after is not None and self._read >= self._fail_after:
            raise ConnectionError("client went away")
        chunk = self.file.read(n)
        self._read += len(chunk)
        return chunk


def test_failed_upload_does_not_destroy_the_file_that_was_already_there(db, uploads):
    game = Game(name="Foo", igdb_id=0); db.add(game); db.commit()
    existing = _file(uploads / "local" / "foo" / CAT.value / "save.dat", b"precious old content")

    with pytest.raises(Exception):
        asyncio.run(storage.upload_and_register_file(
            db, game, _Upload(b"x" * 100_000, fail_after=8192), "save", "save.dat", category=CAT))

    assert existing.read_bytes() == b"precious old content"
    assert list(existing.parent.glob(".*.part")) == [], "no temp files left behind"


def test_failed_upload_of_a_new_file_leaves_nothing_behind(db, uploads):
    game = Game(name="Foo", igdb_id=0); db.add(game); db.commit()

    with pytest.raises(Exception):
        asyncio.run(storage.upload_and_register_file(
            db, game, _Upload(b"x" * 100_000, fail_after=8192), "save", "new.dat", category=CAT))

    folder = uploads / "local" / "foo" / CAT.value
    assert not folder.exists() or list(folder.iterdir()) == []


def test_successful_upload_is_complete_and_registered(db, uploads):
    game = Game(name="Foo", igdb_id=0); db.add(game); db.commit()

    rec = asyncio.run(storage.upload_and_register_file(
        db, game, _Upload(b"y" * 50_000), "rom", "ok.bin", category=CAT))

    path = Path(rec.path)
    assert path.read_bytes() == b"y" * 50_000 and rec.size == 50_000
    assert list(path.parent.glob(".*.part")) == []


# ------------------------------------------------------------ deleting a game

def test_deleting_a_game_never_deletes_files_records_or_covers(db, uploads):
    """
    Copies of the same game share their files (patches, manuals, covers), so removing one
    copy must leave everything in place. This is intentional -- do not "clean up" here.
    """
    damaged = Game(name="Zelda (damaged disc)", igdb_id=77, cover_cached=True)
    good = Game(name="Zelda (good disc)", igdb_id=77, cover_cached=True)
    db.add_all([damaged, good]); db.commit()
    manual = _file(uploads / "igdb" / "77" / "manual" / "manual.pdf")
    cover = _file(uploads / "igdb" / "77" / "metadata" / "cover.jpg")
    rec = _record(db, "77", manual)

    assert game_utils.delete_game(db, damaged.id) is True

    assert manual.exists() and cover.exists(), "the other copy still needs these files"
    assert db.get(GameFile, rec.id) is not None
    assert db.get(Game, good.id) is not None

    # Even the last copy's files stay: re-adding the game re-attaches them.
    assert game_utils.delete_game(db, good.id) is True
    assert manual.exists() and cover.exists() and db.get(GameFile, rec.id) is not None


# ------------------------------------------- deleting a game WITH its files (opt-in)

class FakeS3Bucket(FakeS3):
    """FakeS3 plus listing and batch delete, for prefix-based cleanup."""

    def get_paginator(self, name):
        outer = self

        class _P:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k} for k in sorted(outer.objects) if k.startswith(Prefix)]}
        return _P()

    def delete_objects(self, Bucket, Delete):
        for o in Delete["Objects"]:
            self.deleted.append(o["Key"])
            self.objects.pop(o["Key"], None)


def _two_copies(db, uploads):
    damaged = Game(name="Zelda (damaged)", igdb_id=77, cover_cached=True)
    good = Game(name="Zelda (good)", igdb_id=77, cover_cached=True)
    other = Game(name="Mario", igdb_id=88, cover_cached=True)
    db.add_all([damaged, good, other]); db.commit()
    manual = _file(uploads / "igdb" / "77" / "manual" / "manual.pdf")
    cover = _file(uploads / "igdb" / "77" / "metadata" / "cover.jpg")
    unregistered = _file(uploads / "igdb" / "77" / "patch" / "never_registered.ips")
    mario = _file(uploads / "igdb" / "88" / "manual" / "mario.pdf")
    rec77 = _record(db, "77", manual, size=1000)
    rec88 = _record(db, "88", mario, size=5)
    return damaged, good, other, manual, cover, unregistered, mario, rec77, rec88


def test_delete_with_files_removes_them_for_every_copy_but_only_for_that_game(db, uploads):
    damaged, good, other, manual, cover, unregistered, mario, rec77, rec88 = _two_copies(db, uploads)

    assert game_utils.delete_game(db, damaged.id, delete_files=True) is True

    assert not (uploads / "igdb" / "77").exists(), "the whole folder goes, including unregistered files"
    assert db.query(GameFile).filter(GameFile.game == "77").count() == 0
    db.refresh(good)
    assert good.cover_cached is False, "the surviving copy must not claim a cover that was removed"
    assert db.get(Game, good.id) is not None, "other copies stay in the library"
    # an unrelated game is untouched
    assert mario.exists() and db.get(GameFile, rec88.id) is not None
    db.refresh(other)
    assert other.cover_cached is True


def test_delete_without_the_flag_still_keeps_everything(db, uploads):
    damaged, good, other, manual, cover, unregistered, mario, rec77, rec88 = _two_copies(db, uploads)
    game_utils.delete_game(db, damaged.id)  # default: no files touched
    assert manual.exists() and cover.exists() and unregistered.exists()
    assert db.get(GameFile, rec77.id) is not None
    db.refresh(good)
    assert good.cover_cached is True


def test_failed_commit_deletes_no_files(db, uploads, monkeypatch):
    damaged, good, other, manual, cover, unregistered, mario, rec77, rec88 = _two_copies(db, uploads)
    _fail_commit(db, monkeypatch)

    with pytest.raises(RuntimeError):
        game_utils.delete_game(db, damaged.id, delete_files=True)

    assert manual.exists() and cover.exists() and unregistered.exists()
    db.rollback()
    assert db.get(GameFile, rec77.id) is not None


def test_delete_with_files_cleans_the_s3_folder_only(db, uploads, monkeypatch):
    fake = FakeS3Bucket({
        "uploads/igdb/77/manual/manual.pdf": b"m", "uploads/igdb/77/metadata/cover.jpg": b"c",
        "uploads/igdb/770/manual/other.pdf": b"must survive (different ref that starts with 77)",
        "uploads/igdb/88/manual/mario.pdf": b"must survive",
    })
    monkeypatch.setattr(game_utils, "_s3_client", lambda db, **kw: fake)
    monkeypatch.setattr(game_utils, "_s3_bucket", lambda db: "bucket")
    monkeypatch.setattr(game_utils, "configured_storage_backend", lambda db: "s3")
    monkeypatch.setattr(storage, "_s3_prefix", lambda db: "")
    g = Game(name="Zelda", igdb_id=77, cover_cached=True); db.add(g); db.commit()
    _s3_record(db, "77", "uploads/igdb/77/manual/manual.pdf")

    game_utils.delete_game(db, g.id, delete_files=True)

    assert set(fake.objects) == {"uploads/igdb/770/manual/other.pdf", "uploads/igdb/88/manual/mario.pdf"}


def test_a_game_with_no_usable_file_ref_cannot_delete_files(db, uploads):
    # "???" reduces to an empty ref, which would otherwise point at the whole uploads/local folder.
    g = Game(name="???", igdb_id=0); db.add(g); db.commit()
    other_games_files = _file(uploads / "local" / "something" / "rom" / "x.bin")

    with pytest.raises(ValueError):
        game_utils.delete_game(db, g.id, delete_files=True)

    assert other_games_files.exists() and db.get(Game, g.id) is not None


def test_delete_impact_reports_files_size_and_other_copies(db, uploads):
    damaged, good, other, manual, cover, unregistered, mario, rec77, rec88 = _two_copies(db, uploads)

    impact = game_utils.get_delete_impact(db, damaged.id)

    assert impact["file_count"] == 1 and impact["total_bytes"] == 1000
    assert impact["has_cover"] is True and impact["can_delete_files"] is True
    assert impact["other_copies"] == [{"id": good.id, "name": "Zelda (good)"}]
    assert game_utils.get_delete_impact(db, 99999) is None
