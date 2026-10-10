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
3. `runner-release.sh prefetch` provisions a lightweight Distribution 3.1.2
   registry pinned by digest. It is bound only to `127.0.0.1:5000`, stores
   blobs in `/opt/talkwise-registry/data`, and has a 128 MiB memory limit.
   The initial registry image is downloaded by the runner and transferred
   over SSH with a SHA256 archive check; the server never pulls it publicly.
4. The runner opens an authenticated SSH tunnel, then `sync-registry.sh`
   copies both GHCR images by digest with Skopeo `--all --preserve-digests`.
   The complete index (including build attestations) is retained. A digest
   file and a hash of the destination's raw manifest must match the build.
   Subsequent copies reuse registry blobs; no full tar of application images
   or local workstation relay is used.
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

The server does not run `docker build`. Local Docker is not part of the
release path either.

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

Only the runner receives `GITHUB_TOKEN` for GHCR. Credentials are passed to
Skopeo through stdin into a temporary auth file and cleaned on exit; no GHCR
credential is transferred to the server. Registry HTTP is used only on
loopback and within SSH. Do not publish port 5000 or configure public access
without a separate TLS/authentication design.

The server needs Docker Compose, Bash, GNU timeout, flock, Python 3 and
python3-yaml. Distribution is intentionally smaller than Harbor for this
single-server use case; no extra domain, database or account system is added.

## Verification And Timings

```powershell
wsl -d Ubuntu-22.04 -- python3 -m unittest discover -s /mnt/f/AnchorOS/6-项目仓库/TalkWise/scripts/tests -v
wsl -d Ubuntu-22.04 -- bash -lc 'cd /mnt/f/AnchorOS/6-项目仓库/TalkWise && shellcheck -x -P scripts scripts/*.sh'
git diff --check
```

The build job runs the deployment behavior tests and ShellCheck before any
build. Tests cover failed transfers, digest/marker/tag mismatches, concurrency,
no-pull switching, partial updates and rollback. They fake only the external
Docker/SSH-registry boundaries; they do not prove production connectivity.

Actions records each job's duration; scripts emit `mirror_duration_seconds`,
`prefetch_duration_seconds` and `switch_duration_seconds`. Each local pull
has a 300-second timeout and one retry, with a 10-second forced-termination
grace. Mirror/prefetch and switch jobs are bounded to 75 and 15 minutes.
The short switch duration is not the total release time. First-time blob
synchronization can still be bandwidth-limited, so measure an actual run.

Retain the registry data for reuse and rollback. Monitor its disk usage;
deletion is disabled and this workflow does not run garbage collection or
prune previous production images automatically. Schedule retention/GC as
separate maintenance before storage becomes scarce.

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
