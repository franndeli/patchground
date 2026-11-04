# Practical interview challenge batch

Date: 2026-11-04. Source baseline: `565f350`.

The eight approved challenges are implemented under `examples/`. The local built-in catalog now
contains fifteen challenges. The [research](../research/practical-interview-challenges.md) records
source limitations; the [implementation brief](../work/interview-challenge-implementation.md)
retains the accepted behavior. Neither document substitutes for the delivered content.

## Authorship and scope

Four isolated Pi authoring workers created two challenges each. Their observed model was
`openai-codex/gpt-6.1-sol`; the requested `opus` alias resolved to that model. Every new manifest
records generated provenance and `prompt_version: interview-batch-v1`. Two separate Pi reviewers
checked correctness/security and maintainability. They were independent contexts, not independent
humans or a multi-model panel.

Each challenge has an original public ticket, runnable starter, visible and hidden checks, an
application-only reference patch, hints, and debrief questions. The public tickets state the
behavior checked privately. The existing pinned environments and canonical TypeScript runner
assets are unchanged. No registry entries, runtime contracts, website layout, or dependencies
were changed for this batch.

## Challenge validation

All eight passed the six Docker validation steps: manifest, build, broken-state failure,
reference success, determinism, and supported editable-test tampering resistance. No step was
`not_run`. Final reference check counts are:

- `config-precedence`: 16 passed.
- `invoice-monthly-summary`: 18 passed.
- `cron-field-expansion`: 87 passed.
- `webhook-retry-scheduling`: 51 passed.
- `draft-edit-isolation`: 18 passed.
- `search-response-ordering`: 21 passed.
- `sliding-window-rate-limit`: 13 passed.
- `transaction-rule-evaluator`: 25 passed.

The coordinator reruns source validation and fresh-session checks through
`tests/integration/test_authoring.py`. Each session's full test identities, statuses, and occurrence
counts must match validation's broken combined baseline, including hidden checks. The workspace
must contain exactly the public workspace and visible-check files. Its Git bytes must remain
unchanged. These checks also cover the existing curated examples.

All challenge execution used `pgnd validate`, `pgnd check`, or `pgnd run` through Docker. Reference
TypeScript applications and starters also passed TypeScript 5.8.3 with `--noEmit --strict --target
ES2022 --module NodeNext --moduleResolution NodeNext`. The compiler was installed at build time
only in disposable authoring environments, not added to shipped runners. These checks do not
change the runtime contract: Vitest still transpiles rather than typechecks learner submissions.

## Review corrections

The reviewers reproduced four findings before correction:

- Long valid cron numerals triggered Python's integer-conversion length limit. The reference now
  normalizes and bounds conversion without restricting the public grammar. New regression checks
  cover leading zeros, oversized steps, and field-specific errors. The original reviewer probes
  now return the expected `(0,)` expansions.
- SQLite could overflow an intermediate invoice sum even when the final total fit signed 64-bit
  storage. The reference now aggregates selected amounts with Python integers. The original
  cancellation probe now returns exactly `1`; visible and hidden checks cover the case.
- The rule evaluator's reference used an invalid TypeScript exhaustiveness narrowing. The original
  reference failed with TS2322/TS2339 while passing runtime checks. The corrected reference preserves
  exhaustiveness and passes the strict compiler invocation.
- The initial session test accepted visible-only failures. It now compares complete outcomes with
  the combined validation baseline. Removing hidden inputs from a disposable session makes that
  exact assertion fail with ten missing outcomes; the normal session passes.

No starter was completed as part of these corrections. Its defects or missing features remain the
learner's task. No checks were weakened to make a reference pass.

## Wheel and website evidence

A fresh Python 3.12 environment outside the checkout installed the candidate wheel without AI
extras. `pgnd list --builtin --json` returned all fifteen IDs. For each of the eight new IDs,
`show`, `start`, and Docker-backed `check` worked. Initial checks failed as intended without
collection errors; hidden materials stayed outside the workspace and Git bytes were unchanged.
The wheel remains a local candidate at version 0.1.0, not a replacement for published 0.1.0.
Its SHA-256 and source-file hashes are in the [structured evidence](interview-batch-evidence.json).

The website build contains all eight entries in `catalog.json` and all eight HTML cards with
public ticket links and generated provenance. The explicit website regression test first failed
against the stale partial build, naming `sliding-window-rate-limit`, then passed after rebuilding.
The CLI regression previously named all eight missing source IDs and now passes. Generic packaging
and catalog tests derive inventory from manifests rather than assuming a fixed total.

`npm --prefix web test` passed all 27 tests. Real-browser smoke passed clipboard readback,
keyboard focus, clipboard failure/unavailability, no-JavaScript readability, and overflow checks at
320, 375, and 1440 pixels in both color preferences. No website styling changed.

## Repository verification and limits

Ruff lint and format checks passed; mypy passed for 69 source files.
The non-Docker suite passed 1,042 tests. The first full Docker attempt passed 114 tests and failed
14 global cleanup assertions because of one exited sandbox container left before this batch began.
Inspection established its earlier creation time and disposable run resources. Only that stopped
run's container, two volumes, and network were removed. The next full attempt, after the session
tests were consolidated, passed 99 of 113 tests. The same 14 cleanup assertions then exposed a
second, older orphan network and its unused volumes. Inspection confirmed that no container used
those resources, and only that identified run's residue was removed.

A preflight then confirmed that no Patchground containers, networks, or volumes remained. All
14 previously failing tests passed on rerun. Thus all 113 final Docker cases passed across the
full attempt and targeted rerun, not in one all-green full invocation. No test or runtime assertion
was relaxed. Both failed attempts remain recorded in the structured evidence.

Reproduce the principal checks from the checkout:

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -m 'not docker'
PATCHGROUND_REQUIRE_DOCKER=1 uv run pytest -m docker
uv run pytest tests/unit/test_interview_batch.py tests/unit/authoring/test_wheel.py
npm --prefix web test
PLAYWRIGHT_CHANNEL=chrome npm --prefix web run test:browser
```

The full Docker suite includes global cleanup assertions and must run without concurrent
Patchground checks against the same Docker engine. Individual source validations are reproducible
with `uv run pgnd validate examples/<id> --json --no-write`.

Both reviewers confirmed closure of their findings after independent reprobes. Raw authoring,
compiler, review, and session records remain private under
`.pi/context/interview-batch/`. The public evidence excludes personal paths, hidden source,
reference bodies, and raw container logs. Automated repetitions and bounded tampering probes are
not proof against arbitrary cheating or all possible failures.

Human difficulty calibration, independent solving, and independent-human learner/author acceptance
remain unverified. No demand or employer-endorsement claim follows from these generated challenges.
This batch does not establish remote CI, deploy the website, publish a package, or create a release.
The last observed public catalog still contained seven challenges; publishing new content requires
its separate approval and versioned CLI-release process.
