#!/usr/bin/env bash
# Runner-side OCI copy through an already established SSH tunnel.
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/remote-release-common.sh"
: "${GHCR_AUTH_FILE:?GHCR_AUTH_FILE is required}"
REGISTRY_TUNNEL_PORT="${REGISTRY_TUNNEL_PORT:-15000}"
[[ "$REGISTRY_TUNNEL_PORT" =~ ^[1-9][0-9]{0,4}$ ]] || die 'invalid tunnel port'
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

sync_image() {
  local source_ref="$1" digest="$2" repository="$3" tag="$4" actual
  local target="127.0.0.1:$REGISTRY_TUNNEL_PORT/$repository"
  timeout --kill-after=10s 1800 skopeo copy --all --preserve-digests --retry-times 2 \
    --src-authfile "$GHCR_AUTH_FILE" --dest-tls-verify=false --digestfile "$work/digest" \
    "docker://${source_ref%:*}@$digest" "docker://$target:$tag"
  [[ "$(cat "$work/digest")" == "$digest" ]] || die "sync digest changed: $repository"
  skopeo inspect --tls-verify=false --raw "docker://$target@$digest" > "$work/manifest"
  actual="sha256:$(sha256sum "$work/manifest" | cut -d ' ' -f1)"
  [[ "$actual" == "$digest" ]] || die "destination manifest digest mismatch: $repository"
  log "mirror verified: $repository@$digest"
}

started_at="$(date +%s)"
sync_image "$BACKEND_IMAGE_REF" "$BACKEND_DIGEST" talkwise-backend "prod-$ROOT_COMMIT"
sync_image "$NEWAPI_IMAGE_REF" "$NEWAPI_DIGEST" talkwise-frontend-host "prod-$ROOT_COMMIT-$NEWAPI_COMMIT"
log "mirror_duration_seconds=$(($(date +%s) - started_at))"
