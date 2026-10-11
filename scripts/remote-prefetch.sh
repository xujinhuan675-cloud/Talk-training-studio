#!/usr/bin/env bash
# Pull only from the nearby registry while the old containers keep serving.
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/remote-release-common.sh"

PULL_TIMEOUT_SECONDS="${PULL_TIMEOUT_SECONDS:-300}"
PULL_RETRIES="${PULL_RETRIES:-1}"
PULL_RETRY_DELAY_SECONDS="${PULL_RETRY_DELAY_SECONDS:-5}"
[[ "$PULL_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || die 'invalid pull timeout'
[[ "$PULL_RETRIES" =~ ^[0-9]+$ && "$PULL_RETRY_DELAY_SECONDS" =~ ^[0-9]+$ ]] || die 'invalid retry configuration'
acquire_release_lock
mkdir -p "$PREFETCH_ROOT"
chmod 700 "$PREFETCH_ROOT"
# Invalidate an earlier attempt before doing any transfer.
rm -f "$PREFETCH_MARKER"
tmp_marker="$(mktemp "$PREFETCH_ROOT/.prefetch.XXXXXX")"
started_at="$(date +%s)"
finish() {
  rm -f "$tmp_marker"
  log "prefetch_duration_seconds=$(($(date +%s) - started_at))"
}
trap finish EXIT

pull_image() {
  local ref="$1" local_image="$2" attempt id
  for ((attempt=0; attempt<=PULL_RETRIES; attempt++)); do
    log "pull attempt $((attempt + 1))/$((PULL_RETRIES + 1)): $ref"
    if timeout --kill-after=10s "$PULL_TIMEOUT_SECONDS" docker pull --platform linux/amd64 "$ref"; then
      id="$(verified_image_id "$ref")" || die "digest/platform verification failed: $ref"
      docker tag "$ref" "$local_image" || die "cannot create tag: $local_image"
      [[ "$(docker image inspect --format '{{.Id}}' "$local_image")" == "$id" ]] || die 'local tag identity mismatch'
      return 0
    fi
    if ((attempt < PULL_RETRIES)); then sleep "$PULL_RETRY_DELAY_SECONDS"; fi
  done
  return 1
}

pull_image "$BACKEND_PULL_REF" "$BACKEND_LOCAL_IMAGE" || die 'backend prefetch failed; old release is unchanged'
pull_image "$NEWAPI_PULL_REF" "$NEWAPI_LOCAL_IMAGE" || die 'frontend host prefetch failed; old release is unchanged'
backend_id="$(verified_image_id "$BACKEND_PULL_REF")" || die 'backend digest unavailable'
newapi_id="$(verified_image_id "$NEWAPI_PULL_REF")" || die 'frontend digest unavailable'
release_manifest "$backend_id" "$newapi_id" > "$tmp_marker"
chmod 600 "$tmp_marker"
mv "$tmp_marker" "$PREFETCH_MARKER"
log "prefetch verified: $PREFETCH_ID"
