#!/usr/bin/env bash
# Run destructive integration tests against a disposable PostgreSQL database.
# This never truncates the configured GameCubby database.

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TEST_DB="gamecubby_integration"

cleanup() {
  docker compose exec -T gamecubby-db bash -lc \
    "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d postgres -c 'DROP DATABASE IF EXISTS ${TEST_DB} WITH (FORCE);'" \
    >/dev/null 2>&1 || true
}
trap cleanup EXIT

run() {
  printf '\n==> %s\n' "$*"
  "$@"
}

run docker compose config --quiet
run docker compose build gamecubby-api
run docker compose up -d --wait gamecubby-db

cleanup
run docker compose exec -T gamecubby-db bash -lc \
  "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d postgres -c 'CREATE DATABASE ${TEST_DB};'"

run docker compose run --rm --no-deps -e "DB_NAME=${TEST_DB}" \
  --entrypoint alembic gamecubby-api upgrade head

run docker compose run --rm --no-deps -e "DB_NAME=${TEST_DB}" \
  -e RUN_POSTGRES_INTEGRATION=1 --entrypoint pytest gamecubby-api \
  tests/test_postgres_integration.py -q

echo
echo "Destructive integration checks passed; the disposable database was removed."
