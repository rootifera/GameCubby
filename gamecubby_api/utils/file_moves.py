"""
Keep stored files consistent with a database transaction.

Files (local folders, S3 objects) can't be rolled back by the database. The rule used
here is: make every change that can be undone *before* the commit, commit, and only
then do the part that can't be undone (deleting the old copies).

    plan = FileMovePlan()
    try:
        plan.move_dir(old, new)            # undone automatically on failure
        plan.copy_s3(client, bucket, a, b)  # copy only; the old key is deleted after commit
        plan.delete_s3_after_commit(client, bucket, a)
        session.commit()
    except Exception:
        session.rollback()
        plan.rollback()
        raise
    plan.finish()
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Callable

_log = logging.getLogger(__name__)


class FileConflictError(ValueError):
    """The destination already holds files that belong to something else; nothing was changed."""


class FileMovePlan:
    def __init__(self) -> None:
        self._undo: list[Callable[[], None]] = []
        self._after_commit: list[Callable[[], None]] = []

    # --- local folders -------------------------------------------------------------

    def move_dir(self, src: Path, dst: Path) -> None:
        """Rename a folder now (atomic on one filesystem); renamed back on rollback."""
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        self._undo.append(lambda: dst.rename(src))

    def copy_dir(self, src: Path, dst: Path) -> None:
        """Copy a folder (the original stays, e.g. other games still use it); removed on rollback."""
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(src, dst)
        except Exception:
            shutil.rmtree(dst, ignore_errors=True)  # don't leave a half-copied folder behind
            raise
        self._undo.append(lambda: shutil.rmtree(dst, ignore_errors=True))

    # --- S3 objects ----------------------------------------------------------------

    def copy_s3(self, client, bucket: str, old_key: str, new_key: str) -> None:
        """Copy an object (never deletes the original); the copy is removed on rollback."""
        client.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": old_key}, Key=new_key)
        self._undo.append(lambda: client.delete_object(Bucket=bucket, Key=new_key))

    def delete_s3_after_commit(self, client, bucket: str, key: str) -> None:
        self._after_commit.append(lambda: client.delete_object(Bucket=bucket, Key=key))

    def delete_dir_after_commit(self, path: Path) -> None:
        self._after_commit.append(lambda: shutil.rmtree(path, ignore_errors=True))

    def after_commit(self, step: Callable[[], None]) -> None:
        """Run `step` once the commit succeeded (failures are logged, never raised)."""
        self._after_commit.append(step)

    # --- outcome -------------------------------------------------------------------

    def rollback(self) -> None:
        """Undo everything done so far, newest first. Never raises: it runs while handling another error."""
        for undo in reversed(self._undo):
            try:
                undo()
            except Exception:
                _log.error("could not undo a file change; the files may need a manual check", exc_info=True)
        self._undo.clear()
        self._after_commit.clear()

    def finish(self) -> None:
        """Run the deferred, irreversible steps once the commit has succeeded."""
        for step in self._after_commit:
            try:
                step()
            except Exception:
                # The data is committed and correct; only a leftover (unreferenced) old copy remains.
                _log.warning("could not remove an old file copy after commit", exc_info=True)
        self._after_commit.clear()
        self._undo.clear()
