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

say "This will SHUT DOWN your services, update code & images, and start them again."
if ! confirm "Proceed"; then
  warn "Aborted by user."
  exit 0
fi

ensure_git_repo
COMPOSE_CMD="$(choose_compose_cmd)"
COMPOSE_FILE="$(pick_compose_file)"

say "Using compose file: ${COMPOSE_FILE}"
say "Using compose command: ${COMPOSE_CMD}"

say "Shutting down services..."
$COMPOSE_CMD -f "$COMPOSE_FILE" down

say "Switching to ${DEFAULT_BRANCH} (or master fallback) and pulling latest..."
checkout_branch "${DEFAULT_BRANCH}"
say "Fetching remote..."
git fetch --all --prune
say "Pulling latest..."
git pull --ff-only

say "Pulling updated images..."
$COMPOSE_CMD -f "$COMPOSE_FILE" pull

say "Starting services in detached mode..."
$COMPOSE_CMD -f "$COMPOSE_FILE" up -d

if confirm "Do you want to run 'docker system prune -f' to clean unused data?"; then
  warn "Running docker system prune (this removes unused images/containers/networks/build cache)."
  docker system prune -f
else
  say "Skipping docker system prune."
fi

say "Update complete."
