# TalkWise GitHub Actions Deployment

This is the deployment path for the TalkWise project only. It covers two
images:

- `talkwise-backend`: the FastAPI training backend from `backend/`.
- `talkwise-frontend-host`: the TalkWise-modified NewAPI web host from the
  tracked `outside-project/new-api-main` submodule. The server uses the local
  runtime tag `talkwise-newapi` for this image.

The separate official NewAPI gateway is intentionally outside this workflow.
It is not built, tagged, pulled, or restarted by TalkWise deployment.

## Flow

1. A push to `main`, or a manual `workflow_dispatch`, starts
   `.github/workflows/deploy.yml` on an Ubuntu-hosted GitHub runner.
2. The runner checks out the tracked NewAPI submodule, builds both images for
   `linux/amd64`, and pushes commit-addressed tags to GHCR.
3. `runner-release.sh prefetch` uploads only the release scripts and sends
   control commands over SSH. It passes a job-scoped, read-only GHCR token
   through stdin, never through argv, logs or a persistent auth file.
   `remote-mirror.sh` runs the transfer on the production server under the
   release lock and invalidates any previous marker for that attempt.
4. `download-oci.py` fetches the immutable OCI index and every referenced
   manifest, config and layer directly from GHCR. aria2 handles concurrent
   segmented downloads, retries, checksums and resume. Completed blobs are
   SHA256/size-checked before reuse from the shared cache at
   `/opt/talkwise-registry/download-cache`; interrupted files retain aria2
   control state. The full application index, including attestations, is
   retained. Skopeo `--all --preserve-digests` copies the verified OCI layout
   into the loopback Distribution registry. Both the copy digest and the raw
   destination manifest hash must match the build.
   Distribution 3.1.2 is pinned by digest, downloaded directly from Docker Hub
   on the server, and checked against its linux/amd64 platform/layer identity
   before adoption. It listens only on `127.0.0.1:5000`, stores registry data
   in `/opt/talkwise-registry/data`, and has a 128 MiB memory limit.
5. `remote-prefetch.sh` pulls from the server-local registry by digest,
   verifies the exact repository digest, platform and image ID, and writes
   an atomic release marker while the current containers keep serving.
   Local runtime tags include both commit and digest prefixes, so rebuilding
   the same commit cannot overwrite a tag used by the previous release.
6. A separate dependent job runs `runner-release.sh switch`. It checks the
   marker, commit identities, digests and local IDs before changing services.
   A server-side lock rejects concurrent release phases. Compose uses
   `--no-build --no-deps --pull never` and exact image IDs for the switch.
   Both configurations are validated before either service is modified.
7. If synchronization or prefetch fails, the current release stays running.
   Partial Compose failures, unhealthy services, image ID mismatches and
   persistence failures restore the previously running image IDs. A rollback
   failure is reported explicitly, never as a successful release.
   Successful image tags are persisted in the server Compose files so an
   ordinary restart does not revert to an old release.

The server does not run `docker build`. There is no runner-to-server image
upload, SSH registry tunnel, image archive relay or fallback to that route.
SSH remains the control plane, not the image data plane. A direct-download
failure stops before switching and preserves the current release.

## GitHub secrets

The repository needs these Actions secrets. Values stay in GitHub's secret
store and are never written to the repository:

- `DEPLOY_SSH_HOST`
- `DEPLOY_SSH_PORT`
- `DEPLOY_SSH_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_SSH_KNOWN_HOSTS`: verified production SSH host keys. The runner
  requires strict host-key verification; obtain this from the trusted local
  `known_hosts` entry, not an unverified scan during deployment.

The prefetch job overrides package permissions to `read`. Its short-lived
`GITHUB_TOKEN` is forwarded over authenticated SSH stdin and used in memory
to request repository-scoped pull tokens. aria2 receives headers through its
stdin job list; credentials are not written to the cache or tool arguments.
Public downloads, including registry bootstrap, use HTTPS. Registry HTTP is
server-loopback only. Do not publish port 5000 or configure public access
without a separate TLS/authentication design.

The server needs Docker Compose, Bash, GNU timeout, flock, Python 3,
python3-yaml, aria2, Skopeo and curl. Missing prerequisites fail explicitly;
the release does not silently install packages or return to SSH uploads.
Distribution is intentionally smaller than Harbor for this
single-server use case; no extra domain, database or account system is added.

## Verification And Timings

```powershell
wsl -d Ubuntu-22.04 -- python3 -m unittest discover -s /mnt/f/AnchorOS/6-项目仓库/TalkWise/scripts/tests -v
wsl -d Ubuntu-22.04 -- bash -lc 'cd /mnt/f/AnchorOS/6-项目仓库/TalkWise && shellcheck -x -P scripts scripts/*.sh'
git diff --check
```

The build job runs the deployment behavior tests and ShellCheck before any
build. Tests cover server-direct orchestration, credential redaction, full OCI
index traversal, cache reuse/corruption, resume markers, failed transfers,
digest/marker/tag mismatches, concurrency, no-pull switching, partial updates
and rollback. External HTTP, aria2, Docker and Skopeo boundaries are controlled
in these tests; they do not prove production connectivity or throughput.

Actions records each job's duration; scripts emit `mirror_duration_seconds`,
`prefetch_duration_seconds` and `switch_duration_seconds`. Each local pull
has a 300-second timeout and one retry, with a 10-second forced-termination
grace. Mirror/prefetch and switch jobs are bounded to 150 and 15 minutes.
The short switch duration is not the total release time. Default download
limits are 8 concurrent blobs with up to 16 connections each. Server environment
settings `DOWNLOAD_CONCURRENT_BLOBS` (1-8), `DOWNLOAD_CONNECTIONS_PER_BLOB`
(1-16) and `DOWNLOAD_TIMEOUT_SECONDS` (1-3600, default 3600 per image) can
adjust those bounds. aria2 retries each download up to five times; rerunning
prefetch obtains fresh auth and resumes the same content-addressed cache.
Within the image deadline, a failed download can obtain a fresh pull token
and resume only missing blobs up to twice; retries never extend that deadline.
GHCR/server connectivity can still be bandwidth-limited; a single recovery
does not prove a permanent throughput guarantee.

Retain registry data and the verified download cache for reuse and rollback.
Both consume disk space; monitor their combined usage. Currently
deletion is disabled and this workflow does not run garbage collection or
prune previous production images automatically. Schedule retention/GC as
separate maintenance before storage becomes scarce.

An existing managed Distribution container is validated and reused locally,
without requiring Docker Hub connectivity on each release.

## Local trigger

After the workflow and secrets are present on the default branch:

```powershell
.\scripts\deploy-server.ps1 -Push
```

To dispatch the workflow without pushing the current commit:

```powershell
.\scripts\deploy-server.ps1
```

Both commands require `gh auth status` to succeed. The `-Push` form requires a
clean worktree, which prevents accidentally deploying uncommitted files.

## Current limitation

The automated path backs up Compose and runtime env files, but does not create
a PostgreSQL dump on every image-only release. Database migrations remain
controlled by the backend container's existing production configuration and
should be backed up separately before schema-changing work.

## First Production Verification: 2026-10-11

- Code commits: `a504f48` and compatibility fix `a0f7ebe`, pushed to `main`.
- Distribution is running on production as `talkwise-registry`, loopback
  port 5000 only. At the end of the failed automated attempts, application
  and official gateway image IDs/start times remained unchanged.
- Run `38071768607` took 43m04s and failed before switching: a tagless
  Docker archive exposed different image IDs on the runner and server.
  The named-import/platform-layer verification fix has a regression test.
- Run `38075841910` built successfully in 2m04s. Synchronization ran 6m55s
  before cancellation; registry storage grew to about 16 MiB without a
  complete image manifest. The end-to-end attempt took 9m06s. No switch ran.
- Those automated attempts did not deploy the business images. The later
  server-direct recovery downloaded and SHA256-verified all OCI artifacts,
  mirrored the original digests, and completed prefetch and production switch.
  Root commit `a0f7ebe` and NewAPI commit `58d07eb` were deployed on
  2026-10-11 at 08:33:56 UTC; the switch took 59 seconds. Both TalkWise
  containers were healthy; the official gateway was not restarted.
- A server-local registry does not remove the runner-to-server cold-upload
  bottleneck. The server-direct aria2/Skopeo path above replaces that upload
  route; digest verification and the existing prefetch/switch safeguards stay
  mandatory. The temporary recovery script is not the official release entry.
