#!/usr/bin/env python3
"""External process boundary for deployment tests; no real Docker or HTTP calls."""
import json
import os
import pathlib
import subprocess
import sys

name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
state_path = pathlib.Path(os.environ["FAKE_STATE"])
state = json.loads(state_path.read_text(encoding="utf-8"))
with pathlib.Path(os.environ["FAKE_LOG"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps([name, *args]) + "\n")


def save():
    state_path.write_text(json.dumps(state), encoding="utf-8")


def image_info(ref, fmt):
    item = state["images"].get(ref) or next(
        (info for info in state["images"].values() if info["id"] == ref), None)
    if item is None:
        sys.exit(1)
    if fmt == "{{.Id}}":
        print(item["id"])
    elif "RepoDigests" in fmt:
        print("\n".join(item["digests"]))
    elif "Architecture" in fmt:
        print("linux/amd64")
    else:
        print(json.dumps([item]))


if name == "timeout":
    while args and (args[0].startswith("-") or args[0].isdigit()):
        args.pop(0)
    sys.exit(subprocess.call(args))
if name == "sleep":
    sys.exit(0)
if name == "scp":
    sys.exit(0)
if name == "ssh":
    command = args[-1]
    if "remote-mirror.sh" in command:
        state["credential_stdin_received"] = sys.stdin.read().strip() == os.environ["GHCR_TOKEN"]
        save()
        sys.exit(1 if state.get("direct_download_failure") else 0)
    sys.exit(0)
if name == "curl":
    sys.exit(1 if state.get("health_failure") and "8012" in args[-1]
             and state["containers"]["talkwise-backend"]["image"] != "old-backend" else 0)
if name != "docker":
    sys.exit(2)
if args[:2] == ["image", "inspect"]:
    fmt = args[args.index("--format") + 1] if "--format" in args else ""
    image_info(args[-1], fmt)
elif args[0] == "pull":
    if state.get("pull_failure"):
        sys.exit(1)
    ref = args[-1]
    digest = os.environ["BACKEND_DIGEST"] if "backend" in ref else os.environ["NEWAPI_DIGEST"]
    state["images"][ref] = {
        "id": "sha256:" + ("c" if "backend" in ref else "d") * 64,
        "digests": [ref.split("@")[0] + "@" + ("sha256:" + "0" * 64 if state.get("digest_mismatch") else digest)],
    }
    save()
elif args[0] == "tag":
    state["images"][args[2]] = state["images"][args[1]]
    save()
elif args[0] == "inspect":
    item = state["containers"].get(args[-1])
    if item is None:
        sys.exit(1)
    fmt = args[args.index("--format") + 1]
    if fmt == "{{.Config.Image}}":
        print(item["image"])
    elif fmt == "{{.Image}}":
        print(state["images"][item["image"]]["id"])
    elif "Health" in fmt:
        print("healthy")
    else:
        print("running")
elif args[0] == "compose":
    if "config" in args:
        sys.exit(0)
    files = [args[i + 1] for i, arg in enumerate(args) if arg == "-f"]
    content = pathlib.Path(files[-1]).read_text(encoding="utf-8")
    image = next(line.split("image:", 1)[1].strip() for line in content.splitlines() if "image:" in line)
    if image.startswith("sha256:"):
        image = next((ref for ref, info in state["images"].items()
                      if info["id"] == image and "@" not in ref), image)
    container = "talkwise-backend" if args[-1] == "backend" else "1Panel-new-api-4jUC"
    state["containers"][container]["image"] = image
    save()
    # Fail after changing the container, like a partial Compose update.
    if state.get("compose_failure") == args[-1] and not image.startswith("old-"):
        sys.exit(1)
    if state.get("running_mismatch") and not image.startswith("old-"):
        state["containers"][container]["image"] = "old-backend" if container == "talkwise-backend" else "old-newapi"
        save()
else:
    print("unsupported fake Docker command:", args, file=sys.stderr)
    sys.exit(2)
