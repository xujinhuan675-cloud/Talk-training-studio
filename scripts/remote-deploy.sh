#!/usr/bin/env bash
# Switch verified local images; no registry access or dependency restarts here.
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/remote-release-common.sh"

TALKWISE_DIR="${TALKWISE_DIR:-/opt/talkwise}"
NEWAPI_DIR="${NEWAPI_DIR:-/opt/1panel/apps/new-api/new-api}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/talkwise-backups}"
BACKEND_SERVICE="${BACKEND_SERVICE:-backend}"
NEWAPI_SERVICE="${NEWAPI_SERVICE:-new-api}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-talkwise-backend}"
NEWAPI_CONTAINER="${NEWAPI_CONTAINER:-1Panel-new-api-4jUC}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-http://127.0.0.1:8012/health}"
NEWAPI_HEALTH_URL="${NEWAPI_HEALTH_URL:-http://127.0.0.1:3030/api/status}"
HEALTH_ATTEMPTS="${HEALTH_ATTEMPTS:-45}"
HEALTH_INTERVAL_SECONDS="${HEALTH_INTERVAL_SECONDS:-2}"
RELEASE_ID="${RELEASE_ID:-$PREFETCH_ID}"
[[ "$RELEASE_ID" =~ ^[a-zA-Z0-9_-]{1,180}$ ]] || die 'invalid release identity'
[[ "$HEALTH_ATTEMPTS" =~ ^[1-9][0-9]*$ && "$HEALTH_INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || die 'invalid health check configuration'
acquire_release_lock

BACKEND_COMPOSE="$TALKWISE_DIR/docker-compose.yml"
NEWAPI_COMPOSE="$NEWAPI_DIR/docker-compose.yml"
BACKUP_DIR="$BACKUP_ROOT/deploy-$RELEASE_ID"
[[ -f "$BACKEND_COMPOSE" && -f "$NEWAPI_COMPOSE" ]] || die 'missing Compose file'
[[ -f "$PREFETCH_MARKER" ]] || die 'missing verified prefetch marker'
backend_id="$(verified_image_id "$BACKEND_PULL_REF")" || die 'backend digest unavailable locally'
newapi_id="$(verified_image_id "$NEWAPI_PULL_REF")" || die 'frontend digest unavailable locally'
cmp -s <(release_manifest "$backend_id" "$newapi_id") "$PREFETCH_MARKER" || die 'prefetch identity is stale or image IDs changed'
[[ "$(docker image inspect --format '{{.Id}}' "$BACKEND_LOCAL_IMAGE")" == "$backend_id" ]] || die 'backend local tag changed'
[[ "$(docker image inspect --format '{{.Id}}' "$NEWAPI_LOCAL_IMAGE")" == "$newapi_id" ]] || die 'frontend local tag changed'

old_backend_id="$(docker inspect --format '{{.Image}}' "$BACKEND_CONTAINER")"
old_newapi_id="$(docker inspect --format '{{.Image}}' "$NEWAPI_CONTAINER")"
old_backend_image="$(docker inspect --format '{{.Config.Image}}' "$BACKEND_CONTAINER")"
old_newapi_image="$(docker inspect --format '{{.Config.Image}}' "$NEWAPI_CONTAINER")"
# Roll back by ID, even if a same-commit deployment reused an existing local tag.
docker image inspect "$old_backend_id" >/dev/null
docker image inspect "$old_newapi_id" >/dev/null
python3 -c 'import yaml' || die 'python3-yaml is required for Compose persistence'
mkdir -p "$BACKUP_ROOT"
mkdir -m 700 "$BACKUP_DIR" || die 'release backup already exists; use a new release identity'
cp -p "$BACKEND_COMPOSE" "$BACKUP_DIR/talkwise-compose.yml"
cp -p "$NEWAPI_COMPOSE" "$BACKUP_DIR/newapi-compose.yml"
[[ ! -f "$TALKWISE_DIR/backend.env" ]] || cp -p "$TALKWISE_DIR/backend.env" "$BACKUP_DIR/backend.env"
[[ ! -f "$NEWAPI_DIR/.env" ]] || cp -p "$NEWAPI_DIR/.env" "$BACKUP_DIR/newapi.env"

work="$(mktemp -d /tmp/talkwise-switch.XXXXXX)"
frontend_touched=false
backend_touched=false
completed=false
switch_started=0

write_override() { printf 'services:\n  %s:\n    image: %s\n    pull_policy: never\n' "$1" "$2" > "$3"; }
write_override "$BACKEND_SERVICE" "$backend_id" "$work/backend.yml"
write_override "$NEWAPI_SERVICE" "$newapi_id" "$work/newapi.yml"

wait_for_health() {
  local container="$1" url="$2" expected_id="$3" attempt state
  for ((attempt=0; attempt<HEALTH_ATTEMPTS; attempt++)); do
    [[ "$(docker inspect --format '{{.Image}}' "$container" 2>/dev/null)" == "$expected_id" ]] || return 1
    state="$(docker inspect --format '{{.State.Status}}' "$container" 2>/dev/null)" || return 1
    [[ "$state" != exited && "$state" != dead ]] || return 1
    if [[ "$state" == running ]] && curl --fail --silent --show-error --max-time 8 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$HEALTH_INTERVAL_SECONDS"
  done
  return 1
}

compose_up() {
  (cd "$1" && timeout --kill-after=10s 120 docker compose -f "$2" -f "$3" up -d --no-build --no-deps --pull never "$4")
}

restore_service() {
  local dir="$1" compose="$2" service="$3" image_id="$4" container="$5" url="$6"
  write_override "$service" "$image_id" "$work/rollback.yml"
  compose_up "$dir" "$compose" "$work/rollback.yml" "$service" && wait_for_health "$container" "$url" "$image_id"
}

finish() {
  local status="$?" rollback_failed=false
  trap - EXIT INT TERM
  if [[ "$completed" != true && ( "$frontend_touched" == true || "$backend_touched" == true ) ]]; then
    log 'switch failed; restoring previous Compose files and exact image IDs'
    cp -p "$BACKUP_DIR/talkwise-compose.yml" "$BACKEND_COMPOSE" || rollback_failed=true
    cp -p "$BACKUP_DIR/newapi-compose.yml" "$NEWAPI_COMPOSE" || rollback_failed=true
    if [[ "$backend_touched" == true ]]; then
      restore_service "$TALKWISE_DIR" "$BACKEND_COMPOSE" "$BACKEND_SERVICE" "$old_backend_id" "$BACKEND_CONTAINER" "$BACKEND_HEALTH_URL" || rollback_failed=true
    fi
    if [[ "$frontend_touched" == true ]]; then
      restore_service "$NEWAPI_DIR" "$NEWAPI_COMPOSE" "$NEWAPI_SERVICE" "$old_newapi_id" "$NEWAPI_CONTAINER" "$NEWAPI_HEALTH_URL" || rollback_failed=true
    fi
    if [[ "$rollback_failed" == true ]]; then log 'ROLLBACK FAILED: manual recovery required'; else log 'rollback verified'; fi
    status=1
  fi
  if ((switch_started > 0)); then log "switch_duration_seconds=$(($(date +%s) - switch_started))"; fi
  rm -rf "$work"
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

persist_image() {
  python3 - "$1" "$2" "$3" <<'PY'
import os
from pathlib import Path
import sys
import yaml
path, service, image = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
data = yaml.safe_load(path.read_text(encoding='utf-8'))
data['services'][service]['image'] = image
data['services'][service]['pull_policy'] = 'never'
temp = path.with_name(path.name + '.tmp')
temp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
os.chmod(temp, path.stat().st_mode & 0o777)
os.replace(temp, path)
PY
}

# Validate both configurations before touching either container.
(cd "$NEWAPI_DIR" && docker compose -f "$NEWAPI_COMPOSE" -f "$work/newapi.yml" config --quiet)
(cd "$TALKWISE_DIR" && docker compose -f "$BACKEND_COMPOSE" -f "$work/backend.yml" config --quiet)
switch_started="$(date +%s)"
frontend_touched=true
compose_up "$NEWAPI_DIR" "$NEWAPI_COMPOSE" "$work/newapi.yml" "$NEWAPI_SERVICE"
wait_for_health "$NEWAPI_CONTAINER" "$NEWAPI_HEALTH_URL" "$newapi_id" || die 'frontend image/health verification failed'
backend_touched=true
compose_up "$TALKWISE_DIR" "$BACKEND_COMPOSE" "$work/backend.yml" "$BACKEND_SERVICE"
wait_for_health "$BACKEND_CONTAINER" "$BACKEND_HEALTH_URL" "$backend_id" || die 'backend image/health verification failed'
persist_image "$BACKEND_COMPOSE" "$BACKEND_SERVICE" "$BACKEND_LOCAL_IMAGE"
persist_image "$NEWAPI_COMPOSE" "$NEWAPI_SERVICE" "$NEWAPI_LOCAL_IMAGE"
(cd "$TALKWISE_DIR" && docker compose -f "$BACKEND_COMPOSE" config --quiet)
(cd "$NEWAPI_DIR" && docker compose -f "$NEWAPI_COMPOSE" config --quiet)
release_manifest "$backend_id" "$newapi_id" > "$BACKUP_DIR/RELEASE-METADATA"
printf '\nold_backend_image=%s\nold_newapi_image=%s\nold_backend_id=%s\nold_newapi_id=%s\ndeployed_at_utc=%s\n' "$old_backend_image" "$old_newapi_image" "$old_backend_id" "$old_newapi_id" "$(date -u +%FT%TZ)" >> "$BACKUP_DIR/RELEASE-METADATA"
chmod 600 "$BACKUP_DIR/RELEASE-METADATA"
completed=true
log "TalkWise deployment succeeded: $PREFETCH_ID"
log "backend_image_id=$backend_id frontend_image_id=$newapi_id backup_dir=$BACKUP_DIR"
