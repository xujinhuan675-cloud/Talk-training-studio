#!/usr/bin/env bash
# SSH carries control commands and scripts only; the server downloads every blob.
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
trap 'rm -rf "$work"' EXIT
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
[[ "$GHCR_USERNAME" =~ ^[a-zA-Z0-9_-]+(\[bot\])?$ ]] || die 'invalid registry username'
ssh_run "install -d -m 700 '$remote/scripts'"
scp "${ssh_options[@]}" -P "$DEPLOY_SSH_PORT" \
  "$(dirname "${BASH_SOURCE[0]}")"/remote-{release-common,prefetch,deploy,registry,mirror}.sh \
  "$(dirname "${BASH_SOURCE[0]}")/download-oci.py" "$destination:$remote/scripts/"
# No credential in argv, the remote environment, or a persistent auth file.
printf '%s' "$GHCR_TOKEN" | ssh_run "$remote_env GHCR_USERNAME='$GHCR_USERNAME' bash '$remote/scripts/remote-mirror.sh'"
ssh_run "$remote_env bash '$remote/scripts/remote-prefetch.sh'"
