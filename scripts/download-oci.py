#!/usr/bin/env python3
"""Fetch immutable OCI artifacts with aria2; mirror verified bytes with Skopeo."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ACCEPT = ",".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
))
DIGEST = re.compile(r"sha256:[a-f0-9]{64}\Z")
REGISTRY_DIGEST = "sha256:ddf754342cfc8acc51a56d5d0ab6af06826461864460636d8bd5c546dab2a7b8"


class DownloadError(RuntimeError):
    pass


def setting(name, default, maximum):
    value = os.environ.get(name, str(default))
    if not value.isdigit() or not 1 <= int(value) <= maximum:
        raise DownloadError("invalid download setting: " + name)
    return int(value)


def identity(value):
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise DownloadError("invalid SHA256 identity")
    return value


def sha256(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def verified(path, digest, size):
    if not path.is_file() or path.with_name(path.name + ".aria2").exists():
        return False
    if path.stat().st_size != size:
        return False
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return "sha256:" + checksum.hexdigest() == digest


def fetch(url, headers):
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read(32 * 1024 * 1024 + 1)
            if len(payload) > 32 * 1024 * 1024:
                raise DownloadError("registry metadata exceeds size limit")
            return payload
        except (OSError, urllib.error.URLError):
            if attempt == 3:
                raise DownloadError("registry metadata request failed") from None
            time.sleep(2)


def run(command, **kwargs):
    try:
        return subprocess.run(command, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, **kwargs)
    except (OSError, subprocess.SubprocessError):
        # Tool output may contain signed URLs or bearer credentials.
        raise DownloadError(command[0] + " failed; verified cache retained for retry") from None


def download_image(source, digest, cache, *, username="", password="", platform_only=False):
    identity(digest)
    match = re.fullmatch(r"(ghcr\.io|docker\.io)/([a-z0-9][a-z0-9._/-]*)", source)
    if not match or any(part in ("", ".", "..") for part in match[2].split("/")):
        raise DownloadError("unsupported source repository")
    if any(character in username + password for character in "\r\n"):
        raise DownloadError("invalid registry credential format")
    host, repository = match.groups()
    service = "ghcr.io" if host == "ghcr.io" else "registry.docker.io"
    token_base = "https://ghcr.io/token" if host == "ghcr.io" else "https://auth.docker.io/token"
    api_host = host if host == "ghcr.io" else "registry-1.docker.io"
    api = "https://" + api_host + "/v2/" + repository
    token_url = token_base + "?" + urllib.parse.urlencode({
        "service": service, "scope": "repository:" + repository + ":pull",
    })
    def authenticate():
        auth = {}
        if username and password and host == "ghcr.io":
            credential = base64.b64encode((username + ":" + password).encode()).decode()
            auth["Authorization"] = "Basic " + credential
        data = json.loads(fetch(token_url, auth))
        token = data.get("token") or data.get("access_token")
        if not isinstance(token, str) or not token or any(c in token for c in "\r\n"):
            raise DownloadError("registry did not issue a pull token")
        return {"Authorization": "Bearer " + token, "Accept": ACCEPT}

    auth = authenticate()
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    blobs = cache / "blobs/sha256"
    blobs.mkdir(parents=True, exist_ok=True)
    layout = cache / "layouts" / hashlib.sha256(source.encode()).hexdigest() / digest[7:]
    layout.mkdir(parents=True, exist_ok=True)
    (layout / "blobs").mkdir(exist_ok=True)
    if not (layout / "blobs/sha256").exists():
        (layout / "blobs/sha256").symlink_to(blobs.resolve(), target_is_directory=True)
    seen = set()
    jobs = []

    def manifest(item, depth=0):
        expected = identity(item["digest"])
        if expected in seen:
            return
        if depth > 8 or len(seen) > 4096:
            raise DownloadError("OCI index exceeds traversal limit")
        seen.add(expected)
        raw = fetch(api + "/manifests/" + expected, auth)
        if sha256(raw) != expected or ("size" in item and len(raw) != item["size"]):
            raise DownloadError("manifest identity mismatch")
        data = json.loads(raw)
        path = blobs / expected[7:]
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(raw)
        temporary.replace(path)
        if "manifests" in data:
            for child in data["manifests"]:
                platform = child.get("platform", {})
                if not platform_only or (platform.get("os"), platform.get("architecture")) == ("linux", "amd64"):
                    manifest(child, depth + 1)
        else:
            for child in [data["config"], *data["layers"]]:
                child_digest = identity(child["digest"])
                size = child["size"]
                if not isinstance(size, int) or size < 0:
                    raise DownloadError("invalid blob size")
                if child_digest in seen:
                    continue
                seen.add(child_digest)
                child_path = blobs / child_digest[7:]
                if not verified(child_path, child_digest, size):
                    jobs.append((child_digest, size, child_path))
        return data, len(raw)

    index, size = manifest({"digest": digest})
    (layout / "oci-layout").write_text(json.dumps({"imageLayoutVersion": "1.0.0"}), encoding="utf-8")
    (layout / "index.json").write_text(json.dumps({"schemaVersion": 2, "manifests": [{
        "mediaType": index["mediaType"], "digest": digest, "size": size,
        "annotations": {"org.opencontainers.image.ref.name": "release"},
    }]}), encoding="utf-8")
    if jobs:
        concurrent = setting("DOWNLOAD_CONCURRENT_BLOBS", 4, 8)
        connections = setting("DOWNLOAD_CONNECTIONS_PER_BLOB", 8, 16)
        timeout = setting("DOWNLOAD_TIMEOUT_SECONDS", 1800, 3600)
        command = ["aria2c", "--input-file=-", "--no-conf=true",
             "--max-concurrent-downloads=" + str(concurrent), "--split=" + str(connections),
             "--max-connection-per-server=" + str(connections), "--min-split-size=1M",
             "--continue=true", "--file-allocation=none", "--check-integrity=true",
             "--auto-file-renaming=false", "--allow-overwrite=true", "--max-tries=5",
             "--retry-wait=3", "--timeout=30", "--connect-timeout=15",
             "--console-log-level=error", "--download-result=hide", "--enable-color=false",
             "--show-console-readout=false"]
        deadline = time.monotonic() + timeout
        for attempt in range(3):
            pending = [(digest, size, path) for digest, size, path in jobs
                       if not verified(path, digest, size)]
            if not pending:
                break
            if attempt:
                auth = authenticate()
            inputs = []
            for blob_digest, _, path in pending:
                inputs.extend([api + "/blobs/" + blob_digest,
                               "  header=" + "Authorization: " + auth["Authorization"],
                               "  dir=" + str(path.parent), "  out=" + path.name,
                               "  checksum=sha-256=" + blob_digest[7:]])
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DownloadError("image download deadline exceeded")
            try:
                run(command, input="\n".join(inputs) + "\n", text=True, timeout=remaining)
                break
            except DownloadError:
                if attempt == 2 or time.monotonic() >= deadline:
                    raise
                print("download_retry_with_fresh_token=" + str(attempt + 1), flush=True)
    for blob_digest, size, path in jobs:
        if not verified(path, blob_digest, size):
            raise DownloadError("downloaded blob identity mismatch")
    print("download_verified=" + source + "@" + digest, flush=True)
    return layout


def mirror_image(layout, digest, target):
    identity(digest)
    if not re.fullmatch(r"127\.0\.0\.1:5000/[a-z0-9._/-]+:[a-zA-Z0-9_.-]+", target):
        raise DownloadError("mirror destination must be the loopback registry")
    with tempfile.TemporaryDirectory() as work:
        digest_file = Path(work) / "digest"
        run(["skopeo", "copy", "--all", "--preserve-digests", "--dest-tls-verify=false",
             "--digestfile", str(digest_file), "oci:" + str(layout) + ":release",
             "docker://" + target], timeout=600)
        if digest_file.read_text(encoding="utf-8").strip() != digest:
            raise DownloadError("mirror changed the source digest")
        ref = target.rsplit(":", 1)[0] + "@" + digest
        result = run(["skopeo", "inspect", "--tls-verify=false", "--raw", "docker://" + ref], timeout=60)
        if sha256(result.stdout) != digest:
            raise DownloadError("destination manifest identity mismatch")
    print("mirror_verified=" + ref, flush=True)


def bootstrap_registry(cache):
    script = Path(__file__).with_name("remote-registry.sh")
    tag = "talkwise-registry-bootstrap:3.1.2"
    try:
        result = run(["docker", "inspect", "--format", "{{.Image}}", "talkwise-registry"], timeout=30)
    except DownloadError:
        result = None
    if result is not None:
        current_id = identity(result.stdout.decode().strip())
        tagged_id = run(["docker", "image", "inspect", "--format", "{{.Id}}", tag], timeout=30)
        if current_id != tagged_id.stdout.decode().strip():
            raise DownloadError("managed registry image differs from pinned bootstrap tag")
        # Existing containers are validated locally, without adding a Docker Hub dependency.
        run(["bash", str(script)], env={**os.environ, "REGISTRY_IMAGE_ID": current_id}, timeout=120)
        print("loopback_registry_reused", flush=True)
        return
    layout = download_image("docker.io/library/registry", REGISTRY_DIGEST, cache, platform_only=True)
    blobs = layout / "blobs/sha256"
    index = json.loads((blobs / REGISTRY_DIGEST[7:]).read_text(encoding="utf-8"))
    child = next(item for item in index["manifests"] if item.get("platform", {}).get("os") == "linux"
                 and item.get("platform", {}).get("architecture") == "amd64")
    manifest = json.loads((blobs / child["digest"][7:]).read_text(encoding="utf-8"))
    config = json.loads((blobs / manifest["config"]["digest"][7:]).read_text(encoding="utf-8"))
    try:
        result = run(["docker", "image", "inspect", tag], timeout=30)
    except DownloadError:
        run(["skopeo", "copy", "--override-os", "linux", "--override-arch", "amd64",
             "oci:" + str(layout) + ":release", "docker-daemon:" + tag], timeout=300)
        result = run(["docker", "image", "inspect", tag], timeout=30)
    image = json.loads(result.stdout)[0]
    if (image["Os"], image["Architecture"], image["RootFS"]["Layers"]) != (
            config["os"], config["architecture"], config["rootfs"]["diff_ids"]):
        raise DownloadError("Distribution platform/layer identity mismatch")
    image_id = identity(image["Id"])
    run(["bash", str(script)],
        env={**os.environ, "REGISTRY_IMAGE_ID": image_id}, timeout=120)
    print("loopback_registry_verified", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", default="/opt/talkwise-registry/download-cache")
    parser.add_argument("--username", default="")
    parser.add_argument("--credential-stdin", action="store_true")
    parser.add_argument("--bootstrap-registry", action="store_true")
    parser.add_argument("--source")
    parser.add_argument("--digest")
    parser.add_argument("--target")
    args = parser.parse_args()
    password = sys.stdin.read(8192).rstrip("\n") if args.credential_stdin else ""
    os.umask(0o077)
    if args.bootstrap_registry:
        bootstrap_registry(args.cache)
    else:
        if not args.source or not args.digest or not args.target:
            raise DownloadError("source, digest and target are required")
        layout = download_image(args.source, args.digest, args.cache,
                                username=args.username, password=password)
        mirror_image(layout, args.digest, args.target)


if __name__ == "__main__":
    try:
        main()
    except DownloadError as error:
        print("OCI transfer failed: " + str(error) + "; application containers unchanged", file=sys.stderr)
        sys.exit(1)
    except (KeyError, ValueError, OSError, StopIteration, TypeError):
        # Avoid echoing provider messages, credentials or signed blob URLs.
        print("OCI transfer failed; cache retained and application containers unchanged", file=sys.stderr)
        sys.exit(1)
