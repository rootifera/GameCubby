# Full API testing with database restoration

Run the comprehensive backend suite with:

```bash
./scripts/test-api-full-with-restore.sh
```

The runner starts PostgreSQL, creates a native `pg_dump -Fc` snapshot of the configured Compose database, runs every test under `tests/` against that database, then stops API/Web containers and restores the snapshot with `pg_restore --clean --if-exists`. Its shell `trap` performs the restoration after test failures and interrupts as well.

The script deletes only its own timestamped pre-test dump after a successful restore. It preserves the database and service running state that existed before the run.

This intentionally tests the PostgreSQL dump/restore path itself. The separate `/backup/` and `/backup/save` API behavior is covered by the integration suite.
