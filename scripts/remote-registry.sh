#!/usr/bin/env bash
# A loopback-only Distribution registry. Application containers are never touched.
set -Eeuo pipefail
: "${REGISTRY_IMAGE_ID:?REGISTRY_IMAGE_ID is required}"
[[ "$REGISTRY_IMAGE_ID" =~ ^sha256:[a-f0-9]{64}$ ]] || exit 1
name=talkwise-registry
data=/opt/talkwise-registry/data
docker image inspect "$REGISTRY_IMAGE_ID" >/dev/null
if docker inspect "$name" >/dev/null 2>&1; then
  # Refuse to adopt or modify an unrelated/misconfigured existing container.
  docker inspect "$name" | python3 -c '
import json, sys
c = json.load(sys.stdin)[0]
assert c["Image"] == sys.argv[1], "registry image changed; explicit maintenance required"
assert c["Config"]["Labels"].get("org.talkwise.role") == "registry", "unmanaged registry"
assert c["HostConfig"]["PortBindings"] == {"5000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5000"}]}, "registry port must remain loopback-only"
assert c["HostConfig"]["NetworkMode"] != "host", "host networking is not allowed"
assert any(m["Source"] == "/opt/talkwise-registry/data" and m["Destination"] == "/var/lib/registry" for m in c["Mounts"]), "registry storage path changed"
' "$REGISTRY_IMAGE_ID"
  [[ "$(docker inspect --format '{{.State.Running}}' "$name")" == true ]] || docker start "$name"
else
  [[ ! -e /opt/talkwise-registry || -d "$data" ]] || { echo 'unexpected registry directory' >&2; exit 1; }
  mkdir -p "$data"
  docker run -d --name "$name" --pull never --restart unless-stopped \
    --memory 128m --cpus 0.5 --label org.talkwise.role=registry \
    --log-opt max-size=10m --log-opt max-file=3 \
    -p 127.0.0.1:5000:5000 -v "$data:/var/lib/registry" \
    -e REGISTRY_STORAGE_DELETE_ENABLED=false "$REGISTRY_IMAGE_ID"
fi
for ((attempt=0; attempt<30; attempt++)); do
  if curl --fail --silent --max-time 2 http://127.0.0.1:5000/v2/ >/dev/null; then
    echo 'registry ready: 127.0.0.1:5000 (SSH access only)'
    exit 0
  fi
  sleep 1
done
echo 'registry readiness failed; application containers are unchanged' >&2
exit 1
