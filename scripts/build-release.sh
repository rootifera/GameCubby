#!/usr/bin/env bash
#
# Build a release image from a CLEAN export of a git commit, verify that it contains no secrets
# or local files, and (only when asked) push it to Docker Hub.
#
#   scripts/build-release.sh                       build + verify HEAD, push nothing
#   scripts/build-release.sh --push                ...then push :prod and :v<version> (asks first)
#   scripts/build-release.sh --ref v3.4.1          build + verify a specific commit / tag / branch
#   scripts/build-release.sh --check-image IMAGE   only verify an existing image (local or pulled)
#
# Why this exists: an image once went to Docker Hub with a .env, a storage/ folder holding two
# database dumps, and a .git directory inside, because `docker build` copied the working folder.
# Building from `git archive` means only committed files can be in the build context, and the
# checks below fail the release if anything sensitive is found anyway -- in the final filesystem
# AND in every layer (a file deleted in a later build step still lives in an earlier layer).
#
# Requires: bash, git, docker (already logged in if you use --push), tar. No other tools.

set -euo pipefail

# ----------------------------- per-repository configuration -----------------------------
IMAGE="rootifera/gamecubby-api"
DOCKERFILE="gamecubby_api/Dockerfile"
VERSION_FILE="gamecubby_api/version.json"
# A command run inside the finished image to prove it starts at all (entrypoint is overridden).
SMOKE_ENTRYPOINT="python"
SMOKE_ARGS=(-c "import gamecubby_api.main")
# -----------------------------------------------------------------------------------------

# Names (as listed by tar, without a leading ./) that must never appear anywhere in the image.
# Matched against paths inside every layer. Order of checks: FORBIDDEN, then minus ALLOWED.
FORBIDDEN_REGEX='^app/\.env($|\.)|^app/(storage|\.git|\.claude|\.idea|\.venv|backups)(/|$)|\.(dump|pgdump|pgc)$|(^|/)session\.key$|(^|/)maintenance\.json$|^storage/.*[^/]$'
ALLOWED_REGEX='^app/\.env\.(default|example|sample)$'

PUSH=0; YES=0; REF="HEAD"; CHECK_ONLY=""; KEEP=0

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
bad()  { printf '  \033[1;31m✗\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 2; }

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --push) PUSH=1 ;;
    --yes|-y) YES=1 ;;
    --ref) REF="${2:?--ref needs a value}"; shift ;;
    --check-image) CHECK_ONLY="${2:?--check-image needs an image name}"; shift ;;
    --keep-temp) KEEP=1 ;;
    -h|--help) usage ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
  shift
done

command -v docker >/dev/null 2>&1 || die "docker not found"
command -v tar >/dev/null 2>&1 || die "tar not found"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/build-release.XXXXXX")"
cleanup() { [ "$KEEP" = 1 ] && echo "kept: $WORK" || rm -rf "$WORK"; }
trap cleanup EXIT

# ------------------------------------------------------------------------------------------
# check_image IMAGE  -> returns 0 if every check passes, 1 otherwise (prints each result)
# ------------------------------------------------------------------------------------------
check_image() {
  local img="$1" failed=0
  docker image inspect "$img" >/dev/null 2>&1 || die "image not found locally: $img (docker pull it first)"
  say "Checking $img"

  # 1. Final filesystem: what a running container would contain.
  local leaks
  leaks="$(docker run --rm --entrypoint sh "$img" -c '
      cd /app 2>/dev/null || exit 0
      for p in .env .env.local .env.production .env.integration.local storage .git .claude .idea .venv backups; do
        [ -e "$p" ] && echo "/app/$p"
      done
      find /app -path /app/node_modules -prune -o \( -name "*.dump" -o -name "*.pgdump" -o -name session.key \) -print 2>/dev/null
      find /storage -type f 2>/dev/null' || true)"
  if [ -n "$leaks" ]; then bad "files that must not ship are present in the image:"; echo "$leaks" | sed 's/^/        /'; failed=1
  else ok "final filesystem: no .env, storage/, .git, dumps, session keys"; fi

  # 2. Every layer: a file removed by a later step is still downloadable from its original layer.
  mkdir -p "$WORK/save"
  docker save "$img" -o "$WORK/image.tar"
  tar -xf "$WORK/image.tar" -C "$WORK/save"
  rm -f "$WORK/image.tar"
  local hits="" f names
  while IFS= read -r f; do
    # Layers are (usually gzipped) tars; manifests/configs are JSON and simply fail to list.
    names="$(tar -tf "$f" 2>/dev/null | sed 's#^\./##' || true)"
    [ -n "$names" ] || continue
    names="$(printf '%s\n' "$names" | grep -E "$FORBIDDEN_REGEX" | grep -vE "$ALLOWED_REGEX" || true)"
    [ -n "$names" ] && hits+="$(printf '%s\n' "$names" | sed "s#^#        $(basename "$f" | cut -c1-12): #")"$'\n'
  done < <(find "$WORK/save" -type f -size +0)
  rm -rf "$WORK/save"
  if [ -n "$hits" ]; then bad "forbidden paths found in image LAYERS (even if deleted later):"; printf '%s' "$hits" | head -20; failed=1
  else ok "all layers: nothing sensitive in any layer"; fi

  # 3. It has a healthcheck (compose waits for it) and actually starts.
  if [ "$(docker image inspect --format '{{if .Config.Healthcheck}}yes{{else}}no{{end}}' "$img")" = yes ]; then ok "healthcheck is defined"
  else bad "no HEALTHCHECK defined"; failed=1; fi
  if docker run --rm --entrypoint "$SMOKE_ENTRYPOINT" "$img" "${SMOKE_ARGS[@]}" >/dev/null 2>&1; then ok "smoke test: the application starts ($SMOKE_ENTRYPOINT ${SMOKE_ARGS[*]})"
  else bad "smoke test FAILED: $SMOKE_ENTRYPOINT ${SMOKE_ARGS[*]}"; failed=1; fi

  return "$failed"
}

if [ -n "$CHECK_ONLY" ]; then
  if check_image "$CHECK_ONLY"; then say "PASSED: $CHECK_ONLY"; exit 0; else warn "FAILED: $CHECK_ONLY must not be published"; exit 1; fi
fi

# ------------------------------------------------------------------------------------------
# build from a clean export of the commit
# ------------------------------------------------------------------------------------------
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "run this from inside the git repository"
cd "$(git rev-parse --show-toplevel)"
SHA="$(git rev-parse --verify "${REF}^{commit}")" || die "unknown ref: $REF"
SHORT="$(git rev-parse --short "$SHA")"

say "Release commit: $SHORT  ($(git log -1 --format=%s "$SHA"))"
if [ -n "$(git status --porcelain)" ]; then
  warn "You have uncommitted changes. They are NOT part of this build (only commit $SHORT is)."
fi
if [ -z "$(git branch -r --contains "$SHA" 2>/dev/null)" ]; then
  warn "Commit $SHORT is not on any remote branch yet. Push it so the image can be traced to GitHub."
fi

mkdir -p "$WORK/src"
git archive "$SHA" | tar -x -C "$WORK/src"
[ -f "$WORK/src/$DOCKERFILE" ] || die "$DOCKERFILE not found in commit $SHORT"
[ -f "$WORK/src/$VERSION_FILE" ] || die "$VERSION_FILE not found in commit $SHORT"
VERSION="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$WORK/src/$VERSION_FILE" | head -1)"
[ -n "$VERSION" ] || die "could not read the version from $VERSION_FILE"

CANDIDATE="$IMAGE:candidate-$SHORT"
say "Building $CANDIDATE (version $VERSION) from a clean export ($(find "$WORK/src" -type f | wc -l) files)"
docker build -q -f "$WORK/src/$DOCKERFILE" \
  --label "org.opencontainers.image.revision=$SHA" \
  --label "org.opencontainers.image.version=$VERSION" \
  -t "$CANDIDATE" "$WORK/src" >/dev/null
ok "built $CANDIDATE"

if ! check_image "$CANDIDATE"; then
  warn "Release checks FAILED. Nothing was tagged or pushed. The candidate image stays local for inspection: $CANDIDATE"
  exit 1
fi

say "All checks passed for $CANDIDATE  (commit $SHORT, version $VERSION)"
if [ "$PUSH" != 1 ]; then
  cat <<EOF

Nothing was pushed. To publish this exact image:
  docker tag $CANDIDATE $IMAGE:prod
  docker tag $CANDIDATE $IMAGE:v$VERSION
  docker push $IMAGE:prod && docker push $IMAGE:v$VERSION
or simply re-run with --push.
EOF
  exit 0
fi

echo
echo "About to push to Docker Hub:  $IMAGE:prod  and  $IMAGE:v$VERSION   (commit $SHORT)"
if [ "$YES" != 1 ]; then
  read -r -p "Push now? [y/N]: " ans || true
  case "${ans,,}" in y|yes) ;; *) warn "Aborted; nothing pushed."; exit 0 ;; esac
fi
docker tag "$CANDIDATE" "$IMAGE:prod"
docker tag "$CANDIDATE" "$IMAGE:v$VERSION"
docker push "$IMAGE:v$VERSION"
docker push "$IMAGE:prod"
say "Published $IMAGE:prod and $IMAGE:v$VERSION. Keep the versioned tag: it is your rollback target."
