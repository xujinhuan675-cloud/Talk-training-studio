# Agentic Vertical Slice Development Loop

This document is the reusable playbook for building TalkWise features with an
orchestrator, focused sub-agents, code graph analysis, and narrow verification.
Use it when a feature touches multiple layers or needs a demo-grade vertical
slice. For tiny one-file fixes, keep the work single-agent.

## Core Principle

Build one user-visible loop at a time.

A good slice has:

1. An entry point: where the user triggers it.
2. A runtime path: how backend services or external adapters process it.
3. Data persistence: what is saved and where.
4. Event propagation: how downstream systems are notified.
5. Frontend feedback: what the user sees.
6. Acceptance: how the team proves the loop works.

Example:

```text
Chat realtime bar
-> PCM audio or transcript fallback
-> /training-studio/realtime
-> OpenAI/local realtime adapter
-> final transcript
-> stakeholder_messages
-> room_event_bus message
-> guidance SSE
-> chat UI/guidance refresh
```

## The Loop

### 1. Confirm The Round Goal

Start by turning the request into one sentence.

Good:

```text
Make realtime voice produce a persisted room message that triggers guidance.
```

Too broad:

```text
Build the realtime voice platform.
```

If there are several priorities, pick one critical path. Do not mix team
operations, analytics, infrastructure, and UI polish into the same round unless
they are required for the selected loop.

### 2. Update The Code Graph

Run an incremental code graph update before changing files and again after the
round. Use it to check:

- which files are already changed;
- which modules are in the blast radius;
- whether the slice is becoming too wide;
- which tests are likely to matter.

If the graph reports high risk, reduce the slice instead of widening the plan.

### 3. Read The Working Tree

Always inspect `git status --short` and relevant diffs before editing.

Rules:

- Do not revert unrelated changes.
- Treat unknown changes as user or generated work.
- If existing work is on the same path, read it and continue with it.
- If unrelated generated files appear, mention them instead of silently folding
  them into the feature.

### 4. Spawn Focused Sub-Agents

Use sub-agents for bounded, parallel investigation or disjoint implementation.
The orchestrator keeps the immediate critical path local.

Good explorer roles:

- Current path explorer: endpoints, services, UI entry, event flow.
- Persistence explorer: domain entity, DTO, ORM, repository, migration, tests.
- Frontend/E2E explorer: UI controls, service contracts, acceptance path.
- External protocol explorer: official docs and adapter boundary.

Worker agents should only be used when the write scope is clear and disjoint.

Prompt shape:

```text
Repo: <path>.
Scope ONLY <narrow topic>.
Inspect <specific layers/files>.
Answer with current path, smallest changes, and targeted tests.
Do not edit files. Do not revert changes.
```

Worker shape:

```text
Repo: <path>.
You own only <files/directories>.
Implement <one bounded behavior>.
You are not alone in the codebase. Do not revert unrelated changes.
List changed files and checks run.
```

Close sub-agents after their result is consumed.

### 5. Keep Integration On The Critical Path

The orchestrator implements the smallest cross-layer join:

- route/service adapter;
- domain/DTO/model mapping;
- event publication;
- frontend service contract;
- one acceptance test.

Avoid repeating explorer work. Trust the result unless a contradiction appears
while integrating.

### 6. Add The Smallest Durable Data Shape

When a slice needs future review, analytics, or guidance, persist structured
metadata. Do not hide machine-readable fields inside text content.

For training/realtime flows, prefer fields like:

- `source`;
- `trainingMode`;
- `provider`;
- `trainingSessionId`;
- `roomId`;
- provider event IDs;
- timestamps;
- item/turn IDs.

Store only whitelisted scalar metadata. Do not store raw provider events or
audio payloads unless there is a specific retention requirement.

### 7. Adapterize External Services

External systems should be optional at development time.

Pattern:

```text
configured provider -> real adapter
no provider/key -> local fallback or disabled path
tests -> dependency override/fake adapter
```

This keeps SQLite/local demos light while allowing production-like paths such as
OpenAI Realtime or Redis to be enabled by configuration.

### 8. Verify Narrowly First

Run the tests that prove the selected loop:

- backend route/service tests;
- repository round-trip tests when schema changes;
- frontend service tests for wire contracts;
- lint/build after TypeScript or React changes;
- one vertical-slice acceptance test using the current test stack.

Do not introduce a new E2E framework just to prove the first version of a loop
unless browser behavior is the main risk. Backend acceptance tests are often
enough for demo-grade server paths.

### 9. Start The App Only When The Slice Needs It

Use local SQLite by default:

```powershell
.\start-dev.ps1 -UseSqlite -SkipInstall -NoBrowser
```

Do not make Docker, Postgres, Redis, or real OpenAI calls mandatory for the
basic demo. Use them only when the current slice explicitly needs them.

### 10. End The Round With A Risk Note

Close with:

- what changed;
- which checks passed;
- which warnings remain;
- what is still not implemented;
- any local environment caveat;
- the next recommended slice.

## Recommended Round Output

Use this short format:

```text
Round goal:
Completed:
Verification:
Local run:
Remaining risks:
Next slice:
```

## Quality Gates

Before calling a slice done:

- Code graph was updated before and after.
- Unknown working-tree changes were not reverted.
- Sub-agent outputs were consumed or closed.
- The feature has a targeted automated check.
- Frontend changes pass lint/build or report specific remaining warnings.
- Schema changes have a migration and repository round-trip coverage.
- External service paths have a fake/override test.

## Common Pitfalls

- Building a horizontal platform before one demo loop works.
- Making Redis/Docker/OpenAI mandatory for every local run.
- Persisting important metadata as prose inside `content`.
- Letting two agents edit the same files.
- Adding broad UI polish while backend persistence is unverified.
- Treating a local SQLite database as migrated just because tables exist.

## Alembic And SQLite Note

SQLite can contain tables created by tests, manual scripts, or previous app
runs even when Alembic has not recorded the current revision in
`alembic_version`. In that state, `alembic upgrade head` may try to replay old
migrations and fail on existing tables.

For local demo databases, fix this intentionally:

1. Inspect the real schema.
2. Apply any missing lightweight columns manually only if preserving data
   matters.
3. Stamp the database to the correct Alembic head only after confirming the
   schema matches.
4. For throwaway demo data, recreating the SQLite file is often simpler.

Do not run destructive resets on a shared or valuable local database without
explicit approval.
