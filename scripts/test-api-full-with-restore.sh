#!/usr/bin/env bash
# Run the full API suite against the configured Compose database safely.
# The database is restored from a native PostgreSQL dump in all exit paths.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%d_%H%M%S)"
BACKUP_REL="integration-pretest-${STAMP}.dump"
BACKUP_HOST_PATH="$ROOT/storage/backups/$BACKUP_REL"
RESTORE_NEEDED=false
API_WAS_RUNNING=false
WEB_WAS_RUNNING=false

say() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; }

service_running() {
  [[ "$(docker compose ps -q "$1")" != "" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$(docker compose ps -q "$1")")" == "true" ]]
}

restore() {
  local result=$?
  local restore_result=0
  trap - EXIT
  if "$RESTORE_NEEDED" && [[ -f "$BACKUP_HOST_PATH" ]]; then
    say "Restoring the pre-test PostgreSQL backup"
    docker compose stop gamecubby-api gamecubby-web >/dev/null 2>&1 || true
    docker compose run --rm --no-deps --entrypoint bash gamecubby-api -lc '
      set -Eeuo pipefail
      export PGPASSWORD="$DB_PASSWORD"
      pg_restore --clean --if-exists --no-owner --no-privileges \
        -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        "/app/storage/backups/'"$BACKUP_REL"'"
    ' || restore_result=1
    docker compose run --rm --no-deps --entrypoint rm gamecubby-api \
      -f "/app/storage/backups/$BACKUP_REL" || restore_result=1
    if "$API_WAS_RUNNING" || "$WEB_WAS_RUNNING"; then
      docker compose up -d gamecubby-api gamecubby-web >/dev/null || restore_result=1
    fi
  fi
  if [[ "$restore_result" -ne 0 ]]; then
    fail "Database restore or backup cleanup failed"
    result=1
  fi
  exit "$result"
}
trap restore EXIT INT TERM

say "Checking Compose configuration and starting PostgreSQL"
docker compose config --quiet
if service_running gamecubby-api; then API_WAS_RUNNING=true; fi
if service_running gamecubby-web; then WEB_WAS_RUNNING=true; fi
docker compose up -d --wait gamecubby-db

say "Creating native PostgreSQL pre-test backup"
mkdir -p storage/backups
docker compose run --rm --no-deps --entrypoint bash gamecubby-api -lc '
  set -Eeuo pipefail
  export PGPASSWORD="$DB_PASSWORD"
  pg_dump -Fc -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -f "/app/storage/backups/'"$BACKUP_REL"'"
'
[[ -s "$BACKUP_HOST_PATH" ]] || { fail "Pre-test backup was not created"; exit 1; }
RESTORE_NEEDED=true

say "Building the API image and executing the full test suite"
docker compose build gamecubby-api
docker compose run --rm --no-deps \
  -e RUN_POSTGRES_INTEGRATION=1 \
  -e RUN_FULL_API_INTEGRATION=1 \
  --entrypoint pytest gamecubby-api tests -q

say "All tests passed; restoration will now verify the backup path"
