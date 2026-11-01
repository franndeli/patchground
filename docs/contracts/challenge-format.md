---
id: patchground-contract-challenge-format
type: architecture-design
status: draft
title: "Contract: challenge format v0.1"
parent: patchground-architecture
---

# Challenge format v0.1

The format is the product: anyone must be able to author a challenge from this contract alone. v0.1 is
deliberately small — one stage, one ticket, one reference solution, one test command.

## Layout

```
<challenge-id>/
├── challenge.yaml        # manifest (required)
├── TICKET.md             # the task as the user sees it (required)
├── workspace/            # starting codebase, copied into each session (required)
├── environment/Dockerfile# runtime image; dependencies installed here
├── checks/visible/       # tests copied into the workspace
├── checks/hidden/        # tests run only by `check`, never copied
├── artifacts/            # optional: logs, screenshots, data shown to the user
├── solution/reference.patch   # never copied into the workspace
├── debrief/questions.md  # optional interviewer prompts
└── verification.json     # written by `pgnd validate`
```

## challenge.yaml

```yaml
spec_version: "0.1"
id: duplicate-charges-on-retry      # matches the folder name
version: 1.0.0                      # semver
title: Duplicate charges after a payment retry
type: debug                         # debug | feature | review | refactor
summary: A retry path charges customers twice. Find the root cause and fix it with a test.
languages: [python]
tags: [idempotency, retries]
difficulty: intermediate            # beginner | intermediate | advanced
timebox_minutes: 45
ai_policy: allowed                  # allowed | forbidden
environment:
  dockerfile: environment/Dockerfile
  services: []                      # optional sidecar images, e.g. ["postgres:16"]
  test_command: pytest -q --junitxml=$PG_RESULTS/junit.xml
checks:
  visible: checks/visible
  hidden: checks/hidden
solution: solution/reference.patch
expected_paths: [src/payments/, tests/]   # optional, for diff-scope outcomes; include where regression tests go
hints:                              # optional, progressive, each reveal is logged
  - Look at what happens when the provider times out but the charge succeeded.
debrief:
  questions: debrief/questions.md
  focus: [debugging_method, test_quality, scope_judgment]   # coaching areas, unweighted
author: {name: Fran Delicado, github: <handle>}
content_license: CC-BY-4.0
provenance: handmade                # handmade | generated
# generated_by: {model: ..., prompt_version: "3"}   # required when provenance: generated, else forbidden
```

Optional: `tags`, `checks.visible`, `expected_paths`, `hints`, `debrief`, `content_license` (default
`CC-BY-4.0`), `provenance` (default `handmade`), `generated_by`; every other key is required. Values
are not coerced: `spec_version` is the string `"0.1"`, `timebox_minutes` an integer.

- Unknown keys are rejected, except keys prefixed `x-`, which are accepted and ignored so experiments
  don't break the schema.
- Every path is relative to the challenge folder and must stay inside it, except `expected_paths`,
  which are relative to `workspace/` (must stay inside it, need not exist; a trailing `/` marks a
  directory).
- `solution` and `checks.hidden` must not be, contain or sit inside `workspace/` or
  `checks.visible`; `checks.visible` must not overlap `workspace/`; the Dockerfile's folder (the build
  context) must not be, contain or sit inside `workspace/`, `solution` or `checks.hidden`.
- `workspace/` and both checks folders hold only regular files and directories (no symlinks, FIFOs,
  sockets or device files) and no `.git` entry at any depth: repository config a challenge ships
  could otherwise run commands on the host when tools touch the copy.
- `test_command` must write JUnit XML to `$PG_RESULTS/junit.xml` — the only results contract, for every
  language — and must work with preinstalled dependencies only (see `patchground-contract-execution`).
- Services are reached by service name on the run network (e.g. `postgres:5432`); credentials come
  from environment variables the challenge declares.
- Generated challenges carry `provenance: generated` plus `generated_by` (model and prompt version),
  and are otherwise indistinguishable from handmade ones.
- `checks.visible` and `checks.hidden` mirror the workspace layout: their files are merged into the
  workspace root (see `patchground-contract-execution`), so a relative path present in two of
  `workspace/`, `checks.visible` and `checks.hidden` is invalid.
- `environment.services` is in the format but the runner does not start services yet: a non-empty
  list fails validation.
- Code inside `workspace/` keeps the license of the project it came from; `content_license` covers
  the rest of the challenge.

## pack.yaml

```yaml
spec_version: "0.1"
name: patchground-core
version: 0.1.0
description: Official curated challenges
challenges: [duplicate-charges-on-retry, flaky-cache-ttl]   # folder names at the pack root
```

## Reserved

Not in v0.1; the runner must not implement them: stages, `ai_policy: trap` (planted AI patches), the
`incident`, `ai-validation` and `design` types, and weighted rubrics.

## Schema

The Pydantic models in `patchground-spec` are the source of truth; JSON Schemas are exported to
`schema/` and versioned with `spec_version`.
