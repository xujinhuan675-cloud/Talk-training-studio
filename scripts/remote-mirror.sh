#!/usr/bin/env bash
# Server-direct transfer with resumable blob cache; never falls back to SSH upload.
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/remote-release-common.sh"
: "${GHCR_USERNAME:?GHCR_USERNAME is required}"
for tool in aria2c skopeo python3 docker curl; do
  command -v "$tool" >/dev/null || die "missing server prerequisite: $tool"
done
acquire_release_lock
mkdir -p "$PREFETCH_ROOT"
chmod 700 "$PREFETCH_ROOT"
rm -f "$PREFETCH_MARKER"
# Bash holds the short-lived credential only in memory and pipes it to Python.
credential="$(head -c 8192)"
[[ -n "$credential" ]] || die 'missing registry pull credential'
script="$(dirname "${BASH_SOURCE[0]}")/download-oci.py"
started_at="$(date +%s)"
record_duration() { log "mirror_duration_seconds=$(($(date +%s) - started_at))"; }
trap record_duration EXIT
python3 "$script" --bootstrap-registry
printf '%s' "$credential" | python3 "$script" --credential-stdin --username "$GHCR_USERNAME" \
  --source "${BACKEND_IMAGE_REF%:*}" --digest "$BACKEND_DIGEST" \
  --target "127.0.0.1:5000/talkwise-backend:prod-$ROOT_COMMIT"
printf '%s' "$credential" | python3 "$script" --credential-stdin --username "$GHCR_USERNAME" \
  --source "${NEWAPI_IMAGE_REF%:*}" --digest "$NEWAPI_DIGEST" \
  --target "127.0.0.1:5000/talkwise-frontend-host:prod-$ROOT_COMMIT-$NEWAPI_COMMIT"
unset credential
