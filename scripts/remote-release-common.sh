#!/usr/bin/env bash
# Shared identity checks for the prefetch/switch boundary. Never source marker files.
set -Eeuo pipefail

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "$*" >&2; exit 1; }

: "${BACKEND_IMAGE_REF:?BACKEND_IMAGE_REF is required}"
: "${NEWAPI_IMAGE_REF:?NEWAPI_IMAGE_REF is required}"
: "${BACKEND_DIGEST:?BACKEND_DIGEST is required}"
: "${NEWAPI_DIGEST:?NEWAPI_DIGEST is required}"
: "${ROOT_COMMIT:?ROOT_COMMIT is required}"
: "${NEWAPI_COMMIT:?NEWAPI_COMMIT is required}"
: "${PREFETCH_ID:?PREFETCH_ID is required}"
[[ "$ROOT_COMMIT" =~ ^[a-f0-9]{40}$ && "$NEWAPI_COMMIT" =~ ^[a-f0-9]{40}$ ]] || die 'invalid commit identity'
[[ "$BACKEND_DIGEST" =~ ^sha256:[a-f0-9]{64}$ && "$NEWAPI_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]] || die 'invalid build digest'
[[ "$PREFETCH_ID" =~ ^[a-zA-Z0-9_-]{1,180}$ ]] || die 'invalid prefetch identity'
[[ "$BACKEND_IMAGE_REF" =~ ^[a-zA-Z0-9./:@_-]+$ && "$NEWAPI_IMAGE_REF" =~ ^[a-zA-Z0-9./:@_-]+$ ]] || die 'invalid source image reference'

SHORT_COMMIT="${ROOT_COMMIT:0:12}"
NEWAPI_SHORT_COMMIT="${NEWAPI_COMMIT:0:12}"
BACKEND_LOCAL_IMAGE="talkwise-backend:prod-${SHORT_COMMIT}-${BACKEND_DIGEST:7:12}"
NEWAPI_LOCAL_IMAGE="talkwise-newapi:prod-${SHORT_COMMIT}-${NEWAPI_SHORT_COMMIT}-${NEWAPI_DIGEST:7:12}"
BACKEND_PULL_REF="127.0.0.1:5000/talkwise-backend@$BACKEND_DIGEST"
NEWAPI_PULL_REF="127.0.0.1:5000/talkwise-frontend-host@$NEWAPI_DIGEST"
PREFETCH_ROOT="${PREFETCH_ROOT:-/opt/talkwise-backups/prefetch}"
export PREFETCH_MARKER="$PREFETCH_ROOT/$PREFETCH_ID"
export BACKEND_PULL_REF NEWAPI_PULL_REF
DEPLOY_LOCK_FILE="${DEPLOY_LOCK_FILE:-/opt/talkwise-backups/deploy.lock}"

acquire_release_lock() {
  mkdir -p "$(dirname "$DEPLOY_LOCK_FILE")"
  exec 9>"$DEPLOY_LOCK_FILE"
  flock -n 9 || die 'another TalkWise release phase is running'
}

verified_image_id() {
  local ref="$1" id
  docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$ref" | grep -Fxq "$ref" || return 1
  [[ "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$ref")" == linux/amd64 ]] || return 1
  id="$(docker image inspect --format '{{.Id}}' "$ref")" || return 1
  [[ "$id" =~ ^sha256:[a-f0-9]{64}$ ]] || return 1
  printf '%s\n' "$id"
}

release_manifest() {
  python3 - "$PREFETCH_ID" "$ROOT_COMMIT" "$NEWAPI_COMMIT" "$BACKEND_IMAGE_REF" "$NEWAPI_IMAGE_REF" \
    "$BACKEND_DIGEST" "$NEWAPI_DIGEST" "$BACKEND_LOCAL_IMAGE" "$NEWAPI_LOCAL_IMAGE" "$1" "$2" <<'PY'
import json
import sys
keys = ('prefetch_id', 'root_commit', 'newapi_commit', 'backend_image_ref', 'newapi_image_ref',
        'backend_digest', 'newapi_digest', 'backend_local_image', 'newapi_local_image',
        'backend_image_id', 'newapi_image_id')
print(json.dumps(dict(schema=1, **dict(zip(keys, sys.argv[1:]))), sort_keys=True))
PY
}
