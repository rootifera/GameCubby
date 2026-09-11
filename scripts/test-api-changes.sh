#!/usr/bin/env bash
# Validate the API changes without writing to the application database.
#
# Usage:
#   ./scripts/test-api-changes.sh
#   ./scripts/test-api-changes.sh --smoke
#
# --smoke also checks the already-running API. It does not create games, call
# IGDB, run a file sync, or invoke a backup.

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SMOKE=false
if [[ "${1:-}" == "--smoke" ]]; then
  SMOKE=true
elif [[ $# -ne 0 ]]; then
  echo "Usage: $0 [--smoke]" >&2
  exit 2
fi

run() {
  printf '\n==> %s\n' "$*"
  "$@"
}

run docker compose config --quiet
run docker compose build gamecubby-api

if "$SMOKE"; then
  # Test the freshly built image, rather than an older API container that may
  # still be running from before this script started.
  run docker compose up -d --force-recreate gamecubby-api
fi

run docker compose run --rm --no-deps --entrypoint python gamecubby-api \
  -m compileall -q gamecubby_api alembic scripts

run docker compose run --rm --no-deps --entrypoint pytest gamecubby-api \
  tests/test_search_limits.py tests/test_igdb_query_safety.py tests/test_igdb_retry.py -q

run docker compose run --rm --no-deps --entrypoint python gamecubby-api -c '
from gamecubby_api.main import app

schema = app.openapi()
assert "/health/ready" in schema["paths"]
assert "post" in schema["paths"]["/company/sync"]
operation = schema["paths"]["/company/sync"]["post"]
assert operation.get("security"), "company sync must require admin authentication"
print("OpenAPI exposes readiness and protects company sync")
'

if "$SMOKE"; then
  ready=false
  for _attempt in $(seq 1 30); do
    if docker compose exec -T gamecubby-api \
      curl -fsS http://127.0.0.1:8000/health/ready >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 1
  done
  if ! "$ready"; then
    echo "The recreated API did not become ready within 30 seconds." >&2
    docker compose logs --tail=100 gamecubby-api >&2
    exit 1
  fi

  run docker compose exec -T gamecubby-api \
    curl -fsS http://127.0.0.1:8000/health/ready

  status="$(docker compose exec -T gamecubby-api \
    curl -sS -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8000/company/sync)"
  if [[ "$status" != "401" && "$status" != "403" ]]; then
    echo "Expected unauthenticated POST /company/sync to return 401 or 403, got $status" >&2
    exit 1
  fi
  echo "Unauthenticated company sync is rejected with HTTP $status"

  # This is a real, scoped S3 round trip when file storage is configured for
  # S3. The generated object is outside the managed uploads prefix and is
  # deleted in a finally block.
  docker compose exec -T gamecubby-api python - <<'PY'
from uuid import uuid4

from gamecubby_api.utils.db_tools import with_db
from gamecubby_api.utils.storage import _s3_bucket, _s3_client, _s3_prefix, configured_storage_backend

with with_db() as db:
    if configured_storage_backend(db) != "s3":
        print("S3 probe skipped: file storage backend is local")
    else:
        bucket = _s3_bucket(db)
        prefix = _s3_prefix(db)
        key = "/".join(part for part in (prefix, "integration-probes", f"{uuid4()}.txt") if part)
        client = _s3_client(db)
        try:
            client.put_object(Bucket=bucket, Key=key, Body=b"GameCubby integration probe")
            head = client.head_object(Bucket=bucket, Key=key)
            assert head["ContentLength"] == len(b"GameCubby integration probe")
        finally:
            client.delete_object(Bucket=bucket, Key=key)
        print("S3 upload, metadata lookup, and cleanup passed")
PY
fi

echo
echo "All requested API checks passed."
