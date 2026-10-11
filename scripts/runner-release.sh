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
started_at="$(date +%s)"
mirror_seconds=0
prefetch_seconds=0
mirror_attempts=0
finish() {
  local status="$?" result=success
  [[ "$status" == 0 ]] || result=failure
  if [[ "$status" != 0 && "${GITHUB_ACTIONS:-}" == true ]]; then
    printf '::error::TalkWise %s failed (exit %s); inspect phase logs before retrying.\n' "$mode" "$status"
  fi
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    {
      printf '### TalkWise %s: %s\n\n' "$mode" "$result"
      printf '| Phase | Seconds |\n| --- | ---: |\n'
      printf '| %s | %s |\n' "$mode" "$(($(date +%s) - started_at))"
      if [[ "$mode" == prefetch ]]; then
        printf '| Mirror | %s |\n| Local prefetch | %s |\n' "$mirror_seconds" "$prefetch_seconds"
        printf '\nMirror attempts | %s\n' "$mirror_attempts"
      fi
      printf '\nCommit: %s\n' "$ROOT_COMMIT"
      if [[ "$mode" == prefetch && "$status" != 0 && "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]]; then
        printf '\nResume verified cache: gh run rerun %s --failed (reuse build outputs).\n' "$GITHUB_RUN_ID"
      fi
    } >> "$GITHUB_STEP_SUMMARY" || log 'could not write Actions summary; release exit status is preserved'
  fi
  rm -rf "$work"
  exit "$status"
}
trap finish EXIT
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
mirror_started="$(date +%s)"
for mirror_attempts in 1 2; do
  status=0
  printf '%s' "$GHCR_TOKEN" | ssh_run "$remote_env GHCR_USERNAME='$GHCR_USERNAME' bash '$remote/scripts/remote-mirror.sh'" || status="$?"
  mirror_seconds="$(($(date +%s) - mirror_started))"
  if [[ "$status" == 0 ]]; then break; fi
  # Only a bounded download timeout can safely resume automatically.
  if [[ "$status" != 75 || "$mirror_attempts" == 2 ]]; then exit "$status"; fi
  log 'download timed out; resuming the same digests once with retained cache'
  if [[ "${GITHUB_ACTIONS:-}" == true ]]; then
    printf '::warning::Download timed out; resuming verified cache once without rebuilding.\n'
  fi
done
prefetch_started="$(date +%s)"
status=0
ssh_run "$remote_env bash '$remote/scripts/remote-prefetch.sh'" || status="$?"
prefetch_seconds="$(($(date +%s) - prefetch_started))"
exit "$status"
