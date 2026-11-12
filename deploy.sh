#!/usr/bin/env bash
set -euo pipefail

DEFAULT_BRANCH="main"
COMPOSE_FILES=("docker-compose.yml" "compose.yml")

say() { printf "\033[1;36m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[!]\033[0m %s\n" "$*"; }
err() { printf "\033[1;31m[✗]\033[0m %s\n" "$*" >&2; }
confirm() {
  local prompt="${1:-Are you sure?} [y/N]: "
  read -r -p "$prompt" ans || true
  case "${ans,,}" in
    y|yes) return 0 ;;
    *)     return 1 ;;
  esac
}

have_cmd() { command -v "$1" >/dev/null 2>&1; }

choose_compose_cmd() {
  if have_cmd docker && docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif have_cmd docker-compose; then
    echo "docker-compose"
  else
    err "Neither 'docker compose' nor 'docker-compose' found."
    exit 1
  fi
}

pick_compose_file() {
  for f in "${COMPOSE_FILES[@]}"; do
    if [[ -f "$f" ]]; then
      echo "$f"
      return 0
    fi
  done
  err "No docker compose file found (looked for: ${COMPOSE_FILES[*]})."
  exit 1
}

ensure_git_repo() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    err "Not inside a Git repository. Run this script from your project root."
    exit 1
  fi
}

checkout_branch() {
  local target="${1}"
  if ! git show-ref --verify --quiet "refs/heads/${target}"; then
    warn "Branch '${target}' not found locally. Trying 'master'..."
    target="master"
    if ! git show-ref --verify --quiet "refs/heads/${target}"; then
      err "Neither '${DEFAULT_BRANCH}' nor 'master' exists locally."
      exit 1
    fi
  fi

  say "Checking out '${target}'"
  git checkout "${target}"
}

ensure_clean_worktree() {
  if [[ -n "$(git status --porcelain)" ]]; then
    err "Working tree has uncommitted changes. Commit or stash them before updating."
    exit 1
  fi
}

# Safety net: snapshot the database BEFORE pulling anything. The API runs
# `alembic upgrade head` on every start, so a bad migration would otherwise change the
# schema with nothing to roll back to. The dump is a normal backup (checksummed), so it
# shows up on the Backups page and can be restored from there.
PREUPDATE_DB_CONTAINER="gamecubby-db"
PREUPDATE_KEEP=5
backup_before_update() {
  local dir="storage/backups" stamp file
  if ! docker inspect -f '{{.State.Running}}' "$PREUPDATE_DB_CONTAINER" 2>/dev/null | grep -q true; then
    warn "Database container '$PREUPDATE_DB_CONTAINER' is not running; skipping pre-update backup."
    return 0
  fi
  mkdir -p "$dir"
  stamp="$(date -u +%Y%m%d_%H%M%S)"
  file="$dir/preupdate_gamecubby_${stamp}.dump"

  say "Backing up the database before updating -> $file"
  # The DB container's own pg_dump is used, so its version always matches the server.
  if docker exec "$PREUPDATE_DB_CONTAINER" sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$file.partial" \
     && [[ -s "$file.partial" ]] \
     && docker exec -i "$PREUPDATE_DB_CONTAINER" pg_restore --list < "$file.partial" >/dev/null; then
    mv "$file.partial" "$file"
    ( cd "$dir" && sha256sum "$(basename "$file")" > "$(basename "$file").sha256" )
    say "Backup saved ($(du -h "$file" | cut -f1)), verified readable."
    # Keep only the newest few pre-update dumps.
    # shellcheck disable=SC2012
    ls -1t "$dir"/preupdate_gamecubby_*.dump 2>/dev/null | tail -n +$((PREUPDATE_KEEP + 1)) | while read -r old; do
      rm -f "$old" "$old.sha256"
    done
    return 0
  fi

  rm -f "$file.partial"
  err "Pre-update database backup FAILED."
  confirm "Continue updating WITHOUT a backup" || { warn "Aborted; nothing was changed."; exit 1; }
}

ENV_FILE=".env"
ENV_TEMPLATE=".env.default"

# ask "Prompt" "default" -> echoes the answer (default when empty)
ask() {
  local ans
  read -r -p "$1 [$2]: " ans || true
  echo "${ans:-$2}"
}

ask_yes_no() {
  local ans
  while true; do
    read -r -p "$1 [$2]: " ans || true
    ans="${ans:-$2}"
    case "${ans,,}" in
      y|yes) echo "yes"; return 0 ;;
      n|no)  echo "no";  return 0 ;;
      *) echo "Please answer yes or no." >&2 ;;
    esac
  done
}

random_secret() {
  if have_cmd openssl; then
    openssl rand -hex 16
  else
    LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32
  fi
}

# set_env KEY VALUE -> replaces KEY=... (or a commented #KEY=...) in $ENV_FILE, or appends it.
set_env() {
  local key="$1" value="$2" tmp
  tmp="$(mktemp)"
  if grep -qE "^#?${key}=" "$ENV_FILE"; then
    awk -v k="$key" -v v="$value" '
      !done && $0 ~ "^#?" k "=" { print k "=" v; done=1; next }
      { print }' "$ENV_FILE" > "$tmp"
  else
    { cat "$ENV_FILE"; echo "${key}=${value}"; } > "$tmp"
  fi
  cat "$tmp" > "$ENV_FILE"
  rm -f "$tmp"
}

create_env_file() {
  warn "No ${ENV_FILE} found. Let's create one."
  if [[ ! -f "$ENV_TEMPLATE" ]]; then
    err "Template ${ENV_TEMPLATE} not found; cannot create ${ENV_FILE}."
    exit 1
  fi
  cp "$ENV_TEMPLATE" "$ENV_FILE"
  chmod 600 "$ENV_FILE"

  local web_port proxy db_pw maint_pw autobackups backup_time retention
  web_port="$(ask "Web port to serve GameCubby on" "3000")"
  until [[ "$web_port" =~ ^[0-9]+$ ]] && (( web_port >= 1 && web_port <= 65535 )); do
    warn "Not a valid port."
    web_port="$(ask "Web port to serve GameCubby on" "3000")"
  done

  echo "Behind a reverse proxy with HTTPS (NGINX, HAProxy, ...)? Answer 'no' if you access GameCubby via IP:PORT over HTTP."
  proxy="$(ask_yes_no "Behind an HTTPS reverse proxy?" "no")"
  [[ "$proxy" == "yes" ]] && proxy=true || proxy=false

  echo "Database passwords (leave empty to generate a random one)."
  read -r -s -p "Database password (empty = random): " db_pw || true; echo
  read -r -s -p "Maintenance (backup/restore) role password (empty = random): " maint_pw || true; echo
  [[ -n "$db_pw" ]] || { db_pw="$(random_secret)"; say "Generated a random database password."; }
  [[ -n "$maint_pw" ]] || { maint_pw="$(random_secret)"; say "Generated a random maintenance password."; }

  autobackups="$(ask_yes_no "Enable automatic daily backups?" "yes")"
  set_env WEB_PORT "$web_port"
  set_env PROXY "$proxy"
  set_env DB_PASSWORD "$db_pw"
  set_env MAINT_DB_PASSWORD "$maint_pw"
  set_env AUTOBACKUPS "$autobackups"
  if [[ "$autobackups" == "yes" ]]; then
    backup_time="$(ask "Backup time (UTC, HH:MM)" "03:00")"
    retention="$(ask "Days to keep auto backups" "14")"
    set_env BACKUP_TIME "$backup_time"
    set_env BACKUP_RETENTION_DAYS "$retention"
  fi

  say "Created ${ENV_FILE}. Review it for advanced options (pool sizes, paths, ...)."
  warn "If a database volume already exists from an earlier install, the new DB passwords will NOT apply to it."
}

if [[ ! -f "$ENV_FILE" ]]; then
  create_env_file
  say "Continuing with the deployment."
else
  say "Found ${ENV_FILE}. This will update code and images, then recreate affected services."
  if ! confirm "Proceed"; then
    warn "Aborted by user."
    exit 0
  fi
fi

ensure_git_repo
COMPOSE_CMD="$(choose_compose_cmd)"
COMPOSE_FILE="$(pick_compose_file)"
ensure_clean_worktree

say "Using compose file: ${COMPOSE_FILE}"
say "Using compose command: ${COMPOSE_CMD}"

backup_before_update

say "Switching to ${DEFAULT_BRANCH} (or master fallback) and pulling latest..."
say "Fetching remote..."
git fetch --all --prune
checkout_branch "${DEFAULT_BRANCH}"
say "Pulling latest..."
git pull --ff-only

say "Pulling updated images..."
$COMPOSE_CMD -f "$COMPOSE_FILE" pull

say "Recreating services with the updated code and images..."
$COMPOSE_CMD -f "$COMPOSE_FILE" up -d --remove-orphans

# Wait for the app containers to report healthy so a failed update is noticed now,
# not the next time someone opens the site. (Containers without a healthcheck are skipped.)
say "Waiting for services to become healthy (up to 3 minutes)..."
unhealthy=""
for name in gamecubby-api gamecubby-web; do
  status="none"
  for _ in $(seq 1 90); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$name" 2>/dev/null || echo missing)"
    case "$status" in healthy|none|missing) break ;; esac
    sleep 2
  done
  case "$status" in
    healthy) say "$name is healthy." ;;
    none|missing) warn "$name has no healthcheck / is not running; skipping." ;;
    *) warn "$name is '$status'. Check: docker logs $name"; unhealthy="yes" ;;
  esac
done
[ -z "$unhealthy" ] || warn "Update finished, but at least one service is not healthy."

if confirm "Do you want to run 'docker system prune -f' to clean unused data?"; then
  warn "Running docker system prune (this removes unused images/containers/networks/build cache)."
  docker system prune -f
else
  say "Skipping docker system prune."
fi

say "Deploy complete."
