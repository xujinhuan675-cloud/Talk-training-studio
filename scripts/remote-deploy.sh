#!/usr/bin/env bash
# Pull immutable images and switch the TalkWise backend and frontend host.
# The production server never builds an image in this script.

set -eu

: "${BACKEND_IMAGE_REF:?BACKEND_IMAGE_REF is required}"
: "${NEWAPI_IMAGE_REF:?NEWAPI_IMAGE_REF is required}"
: "${ROOT_COMMIT:?ROOT_COMMIT is required}"
: "${NEWAPI_COMMIT:?NEWAPI_COMMIT is required}"

TALKWISE_DIR="${TALKWISE_DIR:-/opt/talkwise}"
NEWAPI_DIR="${NEWAPI_DIR:-/opt/1panel/apps/new-api/new-api}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/talkwise-backups}"
BACKEND_SERVICE="${BACKEND_SERVICE:-backend}"
NEWAPI_SERVICE="${NEWAPI_SERVICE:-new-api}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-talkwise-backend}"
NEWAPI_CONTAINER="${NEWAPI_CONTAINER:-1Panel-new-api-4jUC}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-http://127.0.0.1:8012/health}"
NEWAPI_HEALTH_URL="${NEWAPI_HEALTH_URL:-http://127.0.0.1:3030/api/status}"
SHORT_COMMIT="${SHORT_COMMIT:-$(printf '%s' "$ROOT_COMMIT" | cut -c1-12)}"
NEWAPI_SHORT_COMMIT="${NEWAPI_SHORT_COMMIT:-$(printf '%s' "$NEWAPI_COMMIT" | cut -c1-12)}"
RELEASE_ID="${RELEASE_ID:-talkwise-prod-$(date -u +%Y%m%d-%H%M%S)-${SHORT_COMMIT}-${NEWAPI_SHORT_COMMIT}}"
BACKEND_LOCAL_IMAGE="talkwise-backend:prod-${SHORT_COMMIT}"
NEWAPI_LOCAL_IMAGE="talkwise-newapi:prod-${SHORT_COMMIT}-${NEWAPI_SHORT_COMMIT}"

BACKEND_COMPOSE="$TALKWISE_DIR/docker-compose.yml"
NEWAPI_COMPOSE="$NEWAPI_DIR/docker-compose.yml"
BACKUP_DIR="$BACKUP_ROOT/deploy-${RELEASE_ID}"
BACKEND_OVERRIDE="$(mktemp /tmp/talkwise-backend.XXXXXX.yml)"
NEWAPI_OVERRIDE="$(mktemp /tmp/talkwise-newapi.XXXXXX.yml)"

cleanup() {
  rm -f "$BACKEND_OVERRIDE" "$NEWAPI_OVERRIDE"
}
trap cleanup EXIT

die() {
  echo "deployment failed: $*" >&2
  exit 1
}

require_file() {
  test -f "$1" || die "missing file: $1"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

require_command docker
require_command curl
require_command awk
require_file "$BACKEND_COMPOSE"
require_file "$NEWAPI_COMPOSE"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
cp -p "$BACKEND_COMPOSE" "$BACKUP_DIR/talkwise-compose.yml"
cp -p "$NEWAPI_COMPOSE" "$BACKUP_DIR/newapi-compose.yml"
if [ -f "$TALKWISE_DIR/backend.env" ]; then
  cp -p "$TALKWISE_DIR/backend.env" "$BACKUP_DIR/backend.env"
fi
if [ -f "$NEWAPI_DIR/.env" ]; then
  cp -p "$NEWAPI_DIR/.env" "$BACKUP_DIR/newapi.env"
fi

old_backend_image="$(docker inspect --format '{{.Config.Image}}' "$BACKEND_CONTAINER" 2>/dev/null || true)"
old_newapi_image="$(docker inspect --format '{{.Config.Image}}' "$NEWAPI_CONTAINER" 2>/dev/null || true)"
test -n "$old_backend_image" || die "cannot determine current backend image"
test -n "$old_newapi_image" || die "cannot determine current frontend host image"
docker image inspect "$old_backend_image" >/dev/null 2>&1 || die "current backend image is unavailable: $old_backend_image"
docker image inspect "$old_newapi_image" >/dev/null 2>&1 || die "current frontend host image is unavailable: $old_newapi_image"

cat > "$BACKEND_OVERRIDE" <<EOF
services:
  $BACKEND_SERVICE:
    image: $BACKEND_LOCAL_IMAGE
EOF
cat > "$NEWAPI_OVERRIDE" <<EOF
services:
  $NEWAPI_SERVICE:
    image: $NEWAPI_LOCAL_IMAGE
EOF

echo "Pulling TalkWise images from GHCR"
docker pull "$BACKEND_IMAGE_REF" >/dev/null
docker pull "$NEWAPI_IMAGE_REF" >/dev/null
docker tag "$BACKEND_IMAGE_REF" "$BACKEND_LOCAL_IMAGE"
docker tag "$NEWAPI_IMAGE_REF" "$NEWAPI_LOCAL_IMAGE"

replace_service_image() {
  file="$1"
  service="$2"
  image="$3"
  tmp="${file}.tmp.$$"
  awk -v service="$service" -v image="$image" '
    function indent(s) { match(s, /^[[:space:]]*/); return RLENGTH }
    {
      level = indent($0)
      if ($0 ~ "^[[:space:]]*" service ":[[:space:]]*$") {
        service_level = level
        in_service = 1
        found_service = 1
        print
        next
      }
      if (in_service && level <= service_level && $0 !~ /^[[:space:]]*$/) {
        in_service = 0
      }
      if (in_service && $0 ~ /^[[:space:]]+image:[[:space:]]*/) {
        prefix = $0
        sub(/image:.*/, "image: " image, prefix)
        print prefix
        replaced = 1
        next
      }
      print
    }
    END {
      if (!found_service || !replaced) exit 3
    }
  ' "$file" > "$tmp" || {
    rm -f "$tmp"
    die "could not replace image for service $service in $file"
  }
  mv "$tmp" "$file"
}

wait_for_health() {
  container="$1"
  url="$2"
  attempt=1
  while [ "$attempt" -le 45 ]; do
    state="$(docker inspect --format '{{.State.Status}}' "$container" 2>/dev/null || true)"
    if [ "$state" = running ] && curl --fail --silent --show-error --max-time 8 "$url" >/dev/null 2>&1; then
      return 0
    fi
    if [ "$state" = exited ] || [ "$state" = dead ]; then
      return 1
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  return 1
}

compose_up() {
  dir="$1"
  compose="$2"
  override="$3"
  service="$4"
  (cd "$dir" && docker compose -f "$compose" -f "$override" config --quiet)
  (cd "$dir" && docker compose -f "$compose" -f "$override" up -d --no-build "$service")
}

restore_service() {
  dir="$1"
  compose="$2"
  service="$3"
  image="$4"
  container="$5"
  url="$6"
  override="$(mktemp /tmp/talkwise-rollback.XXXXXX.yml)"
  printf 'services:\n  %s:\n    image: %s\n' "$service" "$image" > "$override"
  if (cd "$dir" && docker compose -f "$compose" -f "$override" up -d --no-build "$service") && wait_for_health "$container" "$url"; then
    rm -f "$override"
    return 0
  fi
  rm -f "$override"
  return 1
}

restore_all() {
  cp -p "$BACKUP_DIR/talkwise-compose.yml" "$BACKEND_COMPOSE"
  cp -p "$BACKUP_DIR/newapi-compose.yml" "$NEWAPI_COMPOSE"
  restore_service "$TALKWISE_DIR" "$BACKEND_COMPOSE" "$BACKEND_SERVICE" "$old_backend_image" "$BACKEND_CONTAINER" "$BACKEND_HEALTH_URL" || true
  restore_service "$NEWAPI_DIR" "$NEWAPI_COMPOSE" "$NEWAPI_SERVICE" "$old_newapi_image" "$NEWAPI_CONTAINER" "$NEWAPI_HEALTH_URL" || true
}

echo "Switching TalkWise frontend host"
if ! compose_up "$NEWAPI_DIR" "$NEWAPI_COMPOSE" "$NEWAPI_OVERRIDE" "$NEWAPI_SERVICE"; then
  die "frontend host compose update failed"
fi
if ! wait_for_health "$NEWAPI_CONTAINER" "$NEWAPI_HEALTH_URL"; then
  echo "frontend host health check failed; restoring previous image" >&2
  restore_service "$NEWAPI_DIR" "$NEWAPI_COMPOSE" "$NEWAPI_SERVICE" "$old_newapi_image" "$NEWAPI_CONTAINER" "$NEWAPI_HEALTH_URL" || true
  exit 1
fi

echo "Switching TalkWise backend"
if ! compose_up "$TALKWISE_DIR" "$BACKEND_COMPOSE" "$BACKEND_OVERRIDE" "$BACKEND_SERVICE"; then
  echo "backend compose update failed; restoring previous images" >&2
  restore_service "$TALKWISE_DIR" "$BACKEND_COMPOSE" "$BACKEND_SERVICE" "$old_backend_image" "$BACKEND_CONTAINER" "$BACKEND_HEALTH_URL" || true
  restore_service "$NEWAPI_DIR" "$NEWAPI_COMPOSE" "$NEWAPI_SERVICE" "$old_newapi_image" "$NEWAPI_CONTAINER" "$NEWAPI_HEALTH_URL" || true
  exit 1
fi
if ! wait_for_health "$BACKEND_CONTAINER" "$BACKEND_HEALTH_URL"; then
  echo "backend health check failed; restoring previous images" >&2
  restore_service "$TALKWISE_DIR" "$BACKEND_COMPOSE" "$BACKEND_SERVICE" "$old_backend_image" "$BACKEND_CONTAINER" "$BACKEND_HEALTH_URL" || true
  restore_service "$NEWAPI_DIR" "$NEWAPI_COMPOSE" "$NEWAPI_SERVICE" "$old_newapi_image" "$NEWAPI_CONTAINER" "$NEWAPI_HEALTH_URL" || true
  exit 1
fi

# Persist the selected local tags so a later ordinary compose restart keeps this release.
if ! replace_service_image "$BACKEND_COMPOSE" "$BACKEND_SERVICE" "$BACKEND_LOCAL_IMAGE" \
  || ! replace_service_image "$NEWAPI_COMPOSE" "$NEWAPI_SERVICE" "$NEWAPI_LOCAL_IMAGE" \
  || ! (cd "$TALKWISE_DIR" && docker compose -f "$BACKEND_COMPOSE" config --quiet) \
  || ! (cd "$NEWAPI_DIR" && docker compose -f "$NEWAPI_COMPOSE" config --quiet); then
  echo "could not persist the selected Compose images; restoring previous release" >&2
  restore_all
  exit 1
fi

backend_digest="$(docker image inspect --format '{{index .RepoDigests 0}}' "$BACKEND_IMAGE_REF" 2>/dev/null || true)"
newapi_digest="$(docker image inspect --format '{{index .RepoDigests 0}}' "$NEWAPI_IMAGE_REF" 2>/dev/null || true)"
cat > "$BACKUP_DIR/RELEASE-METADATA" <<EOF
release_id=$RELEASE_ID
root_commit=$ROOT_COMMIT
newapi_commit=$NEWAPI_COMMIT
backend_image_ref=$BACKEND_IMAGE_REF
backend_local_image=$BACKEND_LOCAL_IMAGE
backend_digest=$backend_digest
newapi_image_ref=$NEWAPI_IMAGE_REF
newapi_local_image=$NEWAPI_LOCAL_IMAGE
newapi_digest=$newapi_digest
deployed_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
chmod 600 "$BACKUP_DIR/RELEASE-METADATA"

echo "TalkWise deployment succeeded"
echo "release_id=$RELEASE_ID"
echo "backend_image=$BACKEND_LOCAL_IMAGE"
echo "frontend_host_image=$NEWAPI_LOCAL_IMAGE"
echo "backup_dir=$BACKUP_DIR"
