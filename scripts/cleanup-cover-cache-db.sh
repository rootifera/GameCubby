#!/usr/bin/env bash
# Remove the temporary cover-cache database change after the cover-cache code
# has been rolled back. Run from the production GameCubby checkout.
set -Eeuo pipefail

if [[ "${1:-}" != "--confirm" ]]; then
  echo "Refusing to modify the database. Re-run with: $0 --confirm" >&2
  exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

stamp="$(date -u +%Y%m%d_%H%M%S)"
backup_rel="cover-cache-cleanup-${stamp}.dump"
backup_host_path="$root/storage/backups/$backup_rel"

mkdir -p storage/backups
docker compose up -d --wait gamecubby-db

echo "Creating native PostgreSQL backup: $backup_rel"
docker compose run --rm --no-deps --entrypoint bash gamecubby-api -lc '
  set -Eeuo pipefail
  export PGPASSWORD="$DB_PASSWORD"
  pg_dump -Fc -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -f "/app/storage/backups/'"$backup_rel"'"
'
[[ -s "$backup_host_path" ]] || { echo "Backup was not created" >&2; exit 1; }

echo "Removing only games.cover_cached_url when present"
docker compose run --rm --no-deps --entrypoint bash gamecubby-api -lc '
  set -Eeuo pipefail
  export PGPASSWORD="$DB_PASSWORD"
  psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<'"'"'SQL'"'"'
BEGIN;
ALTER TABLE games DROP COLUMN IF EXISTS cover_cached_url;
UPDATE alembic_version
SET version_num = '"'"'d8f5a1b3e920'"'"'
WHERE version_num = '"'"'e4f8c2a1d6b3'"'"';
COMMIT;
SQL
'

echo "Database cleanup complete. Backup retained at: $backup_host_path"
