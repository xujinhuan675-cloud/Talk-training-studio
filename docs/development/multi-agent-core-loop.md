# Multi-Agent Core Development Loop

This document is the repo-level playbook for using multiple Codex agents on one feature without losing the core product path. It is a development source of truth, so it lives in this repository instead of AnchorOS project knowledge.

## Goal

Use one orchestrator plus bounded workers to build one feature in slices:

1. Split the work by user-visible capability and file ownership.
2. Let each worker make the smallest core path work first.
3. Run the slice checks immediately.
4. Fix failing checks before expanding the slice.
5. Integrate only after each slice can explain its changed files, checks, failures, and next action.

This is for feature work where parallel agents help. Small one-file fixes should stay single-agent.

## Local References

- `start-dev.ps1` / `start-dev.cmd`: local boot loop for backend, frontend, health checks, and browser launch.
- `backend/infrastructure/external/agent_sdk/`: existing isolated workspace pattern for sub-agents.
- `backend/infrastructure/external/agent_sdk/README.md`: import boundary, workspace isolation, timeout, cleanup, allowed tools, and test contract.
- `backend/pyproject.toml`: backend pytest and quality-tool configuration.
- `frontend/package.json`: frontend dev/build/lint/test commands.
- `.github/workflows/ci.yml` and `.gitlab-ci.yml`: merge-level verification expectations.

## Roles

### Orchestrator

Owns the task boundary, branch/worktree hygiene, integration, and final verification.

The orchestrator should:

- Confirm the true user goal before splitting work.
- Keep the critical path local when waiting would block progress.
- Give each worker a disjoint write scope.
- Prevent workers from reverting unrelated changes.
- Review worker diffs before integrating.
- Run the appropriate core loop after integration.

### Worker

Owns one bounded slice. A worker is not alone in the codebase and must work with nearby changes instead of reverting them.

Worker output must include:

- Changed files.
- Core path implemented.
- Checks run.
- Failures or skipped checks.
- Next fix action, if any.

### Review / Check Agent

Inspects diffs, checks risk, and reports concrete fixes. It should not rewrite the feature unless explicitly assigned a write scope.

## Core-First Loop

Use this loop for each slice:

1. Define the core user behavior in one sentence.
2. Identify the minimum files needed for that behavior.
3. Add or adjust the smallest targeted test.
4. Implement only enough code to pass the core path.
5. Run the slice check.
6. Fix failing behavior before adding polish.
7. Hand back changed files and remaining risk.

Avoid broad refactors, new frameworks, or full redesigns until the core path is passing.

## Split Template

Use this prompt shape when spawning a worker:

```text
You are Worker <name> for <feature>.

Goal:
- <one-sentence core behavior>

Write scope:
- <files or directories this worker owns>

Do not edit:
- <files owned by other workers>

Constraints:
- You are not alone in the codebase. Do not revert unrelated edits.
- Keep the first pass core-only.
- Use existing patterns and tests.

Checks:
- <exact command or script slice>

Final output:
- changed files
- behavior implemented
- checks run
- failures/skips
- next fix action
```

## Example: Training Studio Voice Mode

For the voice training upgrade, split the work like this:

- Worker A: `/training-studio` mode propagation and chat route state.
- Worker B: chat page phone-style practice entry and voice UI state.
- Worker C: backend voice WebSocket path from transcription to chat message and AI reply.
- Worker D: tests and regression review across text, voice, and video modes.

Each worker should make its slice pass before the orchestrator integrates the next slice.

## Fast Checks

Use the local helper for targeted loops:

```powershell
.\scripts\core-loop.ps1 -Slice voice
.\scripts\core-loop.ps1 -Slice frontend
.\scripts\core-loop.ps1 -Slice backend
.\scripts\core-loop.ps1 -Slice agent-sdk
```

Use heavier checks only when the slice is stable:

```powershell
.\scripts\core-loop.ps1 -Slice voice -Full
.\scripts\core-loop.ps1 -Slice frontend -Full -WithLint
.\scripts\core-loop.ps1 -Slice all -Full
```

The default loop is intentionally small. It should answer: does the core slice still work?

## Operating Rules

- Do not print API keys or `.env` contents.
- Do not start Docker or Postgres unless the task explicitly needs it.
- Prefer local SQLite for development.
- Keep worker write scopes disjoint.
- Do not let workers commit, push, or delete user documents unless explicitly asked.
- Use `start-dev.ps1 -UseSqlite` when the feature needs the running app.
- Escalate to full CI-style checks before merge, not before the first core path is alive.

