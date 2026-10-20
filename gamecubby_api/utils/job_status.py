"""
Background jobs (file sync, cover sync, metadata refresh) record their progress in a small JSON
status file and hold a PostgreSQL advisory lock while they run. If the API is killed or restarted
mid-job, the lock vanishes with the process but the status file keeps saying "running" forever,
so the UI shows a job that is not running. At startup we reconcile the two.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .job_lock import try_job_lock

_log = logging.getLogger(__name__)


def reconcile_stale_job_statuses(jobs: Iterable[tuple[Path, str]]) -> list[str]:
    """
    For each (status_file, lock_name): if the file says "running" but the job's lock is free, no one
    is running it any more -> mark it "interrupted". A held lock means a worker really is running
    it (e.g. a rolling restart), so it is left alone. Never raises. Returns the files it fixed.
    """
    fixed: list[str] = []
    for path, lock_name in jobs:
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("status") != "running":
                continue
            with try_job_lock(lock_name) as acquired:
                if not acquired:
                    continue
                data.update(
                    status="interrupted",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    error="Interrupted: the API restarted while this job was running. Start it again if needed.",
                )
                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
                tmp.replace(path)
                fixed.append(str(path))
        except Exception:
            _log.warning("could not reconcile job status file %s", path, exc_info=True)
    return fixed
