import json
from contextlib import contextmanager

from gamecubby_api.utils import job_status


def _write(path, **data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _locks(monkeypatch, free: set):
    """Fake advisory locks: a lock is acquirable only if its name is in `free`."""
    @contextmanager
    def fake(name):
        yield name in free
    monkeypatch.setattr(job_status, "try_job_lock", fake)


def test_a_job_that_died_with_the_api_is_marked_interrupted(tmp_path, monkeypatch):
    status = tmp_path / "s.json"
    _write(status, status="running", kind="refresh", started_at="2026-10-20T10:00:00Z", finished_at=None, error=None)
    _locks(monkeypatch, free={"metadata-refresh"})

    fixed = job_status.reconcile_stale_job_statuses([(status, "metadata-refresh")])

    data = json.loads(status.read_text())
    assert fixed == [str(status)]
    assert data["status"] == "interrupted" and data["finished_at"] and "restarted" in data["error"]
    assert data["kind"] == "refresh" and data["started_at"] == "2026-10-20T10:00:00Z", "other fields are kept"


def test_a_job_really_running_in_another_worker_is_left_alone(tmp_path, monkeypatch):
    status = tmp_path / "s.json"
    _write(status, status="running", started_at="x")
    _locks(monkeypatch, free=set())  # the lock is held by the live job

    assert job_status.reconcile_stale_job_statuses([(status, "cover-image-sync")]) == []
    assert json.loads(status.read_text())["status"] == "running"


def test_finished_idle_missing_and_corrupt_files_are_ignored(tmp_path, monkeypatch):
    done, idle, corrupt = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "c.json"
    _write(done, status="completed", result={"ok": 1})
    _write(idle, status="idle")
    corrupt.write_text("{not json", encoding="utf-8")
    _locks(monkeypatch, free={"j"})

    fixed = job_status.reconcile_stale_job_statuses([(done, "j"), (idle, "j"), (corrupt, "j"), (tmp_path / "nope.json", "j")])

    assert fixed == []
    assert json.loads(done.read_text()) == {"status": "completed", "result": {"ok": 1}}
