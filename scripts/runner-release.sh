#!/usr/bin/env bash
# GitHub runner transport; the registry is reachable only through authenticated SSH.
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/remote-release-common.sh"
: "${DEPLOY_SSH_HOST:?DEPLOY_SSH_HOST is required}"
: "${DEPLOY_SSH_USER:?DEPLOY_SSH_USER is required}"
: "${DEPLOY_SSH_KEY:?DEPLOY_SSH_KEY is required}"
: "${DEPLOY_SSH_KNOWN_HOSTS:?DEPLOY_SSH_KNOWN_HOSTS is required}"
DEPLOY_SSH_PORT="${DEPLOY_SSH_PORT:-22}"
[[ "$DEPLOY_SSH_HOST" =~ ^[a-zA-Z0-9.:-]+$ && "$DEPLOY_SSH_USER" =~ ^[a-zA-Z0-9_-]+$ ]] || die 'invalid SSH destination'
[[ "$DEPLOY_SSH_PORT" =~ ^[1-9][0-9]{0,4}$ ]] || die 'invalid SSH port'
mode="${1:?expected prefetch or switch}"
[[ "$mode" == prefetch || "$mode" == switch ]] || die 'invalid release mode'
work="$(mktemp -d)"
tunnel_pid=''
cleanup() {
  if [[ -n "$tunnel_pid" ]]; then kill "$tunnel_pid" 2>/dev/null || true; wait "$tunnel_pid" 2>/dev/null || true; fi
  rm -rf "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
printf '%s\n' "$DEPLOY_SSH_KEY" > "$work/key"
printf '%s\n' "$DEPLOY_SSH_KNOWN_HOSTS" > "$work/known_hosts"
chmod 600 "$work/key" "$work/known_hosts"
ssh_options=(-i "$work/key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$work/known_hosts" -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4)
destination="$DEPLOY_SSH_USER@$DEPLOY_SSH_HOST"
remote="/opt/talkwise-releases/$PREFETCH_ID"
remote_env="BACKEND_IMAGE_REF='$BACKEND_IMAGE_REF' NEWAPI_IMAGE_REF='$NEWAPI_IMAGE_REF' BACKEND_DIGEST='$BACKEND_DIGEST' NEWAPI_DIGEST='$NEWAPI_DIGEST' ROOT_COMMIT='$ROOT_COMMIT' NEWAPI_COMMIT='$NEWAPI_COMMIT' PREFETCH_ID='$PREFETCH_ID'"
ssh_run() { ssh "${ssh_options[@]}" -p "$DEPLOY_SSH_PORT" "$destination" "$1"; }

if [[ "$mode" == switch ]]; then
  ssh_run "$remote_env bash '$remote/scripts/remote-deploy.sh'"
  exit 0
fi

: "${GHCR_USERNAME:?GHCR_USERNAME is required}"
: "${GHCR_TOKEN:?GHCR_TOKEN is required}"
# Distribution 3.1.2, resolved and pinned on 2026-10-11.
registry_ref='docker.io/library/registry@sha256:ddf754342cfc8acc51a56d5d0ab6af06826461864460636d8bd5c546dab2a7b8'
bootstrap_tag='talkwise-registry-bootstrap:3.1.2'
ssh_run "install -d -m 700 '$remote/scripts'"
scp "${ssh_options[@]}" -P "$DEPLOY_SSH_PORT" \
  "$(dirname "${BASH_SOURCE[0]}")"/remote-{release-common,prefetch,deploy,registry}.sh "$destination:$remote/scripts/"
# Bootstrap the small registry image from the runner, not through server public pulls.
docker pull --platform linux/amd64 "$registry_ref"
identity_format='{{.Os}}/{{.Architecture}} {{json .RootFS.Layers}}'
source_identity="$(docker image inspect --format "$identity_format" "$registry_ref" | sha256sum | cut -d ' ' -f1)"
remote_identity="$(ssh_run "docker image inspect --format '$identity_format' '$bootstrap_tag' 2>/dev/null | sha256sum | cut -d ' ' -f1")"
if [[ "$remote_identity" != "$source_identity" ]]; then
  # Docker classic/containerd stores can expose different .Id values. Preserve a
  # named import and compare platform/layer identity, then use the SERVER's ID.
  docker tag "$registry_ref" "$bootstrap_tag"
  docker save "$bootstrap_tag" | gzip -1 > "$work/registry.tar.gz"
  archive_hash="$(sha256sum "$work/registry.tar.gz" | cut -d ' ' -f1)"
  timeout --kill-after=10s 1200 scp "${ssh_options[@]}" -P "$DEPLOY_SSH_PORT" "$work/registry.tar.gz" "$destination:$remote/registry.tar.gz"
  ssh_run "printf '%s  %s\\n' '$archive_hash' '$remote/registry.tar.gz' | sha256sum -c -"
  ssh_run "set -o pipefail; gzip -dc '$remote/registry.tar.gz' | timeout --kill-after=10s 120 docker load"
  ssh_run "rm -f '$remote/registry.tar.gz'"
fi
remote_identity="$(ssh_run "docker image inspect --format '$identity_format' '$bootstrap_tag' | sha256sum | cut -d ' ' -f1")"
[[ "$remote_identity" == "$source_identity" ]] || die 'Distribution platform/layer identity mismatch after import'
registry_id="$(ssh_run "docker image inspect --format '{{.Id}}' '$bootstrap_tag'")"
[[ "$registry_id" =~ ^sha256:[a-f0-9]{64}$ ]] || die 'invalid server Distribution image ID'
ssh_run "REGISTRY_IMAGE_ID='$registry_id' bash '$remote/scripts/remote-registry.sh'"
ssh "${ssh_options[@]}" -p "$DEPLOY_SSH_PORT" -o ExitOnForwardFailure=yes \
  -N -L 127.0.0.1:15000:127.0.0.1:5000 "$destination" > "$work/tunnel.log" 2>&1 &
tunnel_pid=$!
ready=false
for ((attempt=0; attempt<30; attempt++)); do
  kill -0 "$tunnel_pid" 2>/dev/null || { cat "$work/tunnel.log" >&2; die 'SSH registry tunnel exited'; }
  if curl --fail --silent --max-time 2 http://127.0.0.1:15000/v2/ >/dev/null; then ready=true; break; fi
  sleep 1
done
[[ "$ready" == true ]] || die 'SSH registry tunnel is not ready'
export GHCR_AUTH_FILE="$work/auth.json"
printf '%s' "$GHCR_TOKEN" | skopeo login --authfile "$GHCR_AUTH_FILE" --username "$GHCR_USERNAME" --password-stdin ghcr.io
bash "$(dirname "${BASH_SOURCE[0]}")/sync-registry.sh"
ssh_run "$remote_env bash '$remote/scripts/remote-prefetch.sh'"
