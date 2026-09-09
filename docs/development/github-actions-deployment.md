# TalkWise GitHub Actions Deployment

This is the deployment path for the TalkWise project only. It covers two
images:

- `talkwise-backend`: the FastAPI training backend from `backend/`.
- `talkwise-newapi`: the TalkWise-modified NewAPI web host from the tracked
  `outside-project/new-api-main` submodule.

The separate official NewAPI gateway is intentionally outside this workflow.
It is not built, tagged, pulled, or restarted by TalkWise deployment.

## Flow

1. A push to `main`, or a manual `workflow_dispatch`, starts
   `.github/workflows/deploy.yml` on an Ubuntu-hosted GitHub runner.
2. The runner checks out the tracked NewAPI submodule, builds both images for
   `linux/amd64`, and pushes commit-addressed tags to GHCR.
3. The runner connects to the production server over SSH and streams
   `scripts/remote-deploy.sh`.
4. The server pulls the two GHCR images, backs up its current Compose/env
   files, switches the existing Compose services, and checks both health URLs.
5. If either service fails its health check, the previous image is restored.
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

The server's existing Docker credential for GHCR is used for `docker pull`.
No GHCR token is passed through the GitHub Actions SSH command.

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
