---
id: patchground-contract-verification
type: architecture-design
status: draft
title: "Contract: verification"
parent: patchground-architecture
depends-on: [patchground-contract-challenge-format, patchground-contract-execution]
---

# Verification

"Verified or it doesn't ship." `pgnd validate <path>` proves a challenge is internally consistent inside
its own containers. It is the gate for official packs, community PRs (through `validate-action`) and
generated challenges alike.

## Steps

Run in order; the first one that doesn't hold fails validation with a non-zero exit.

0. **Manifest valid:** `challenge.yaml` passes the schema and every referenced path exists.
1. **Builds:** the image builds from a clean checkout.
2. **Broken state fails:** the starting workspace fails at least one hidden check. The starting
   state runs twice — with visible checks only, then with visible and hidden — and the tests that
   appear only in the second run are the hidden ones. No hidden test, a visible test that vanishes
   in the second run, or an inconclusive run (missing results, limit exceeded) fails the step.
3. **Reference passes:** with `reference.patch` applied, every visible and hidden check passes;
   skipped counts as not passing, and every test seen in step 2 must be present. The patch is a git
   diff relative to `workspace/` (`a/src/...`), applied with `git apply -p1` to a copy, and must
   change at least one file.
4. **Deterministic:** steps 2 and 3 give identical per-test results across 3 runs.
5. **Not trivially gamed:** an empty diff fails, and deleting or skipping the failing tests fails.

On success `validate` writes `verification.json`: the image digest, per-step run results (test ids
and statuses only, never sources or logs) and timestamps. On failure it deletes an existing
Patchground `verification.json`, so a folder never claims a validity it lost. A later image whose
digest differs from the recorded one triggers re-validation; the image id is that of a local build,
so the record is only meaningful on the machine that validated (unconfirmed how packs will carry
proof across machines).

Environment problems (no engine, no git) are not validation failures: they stop `validate` with
exit `2` and no step result (`patchground-contract-cli`).

## What it establishes

The defect is observable by the checks and at least one solution passes them. It does **not** prove the
ticket is complete, that the reference is the only correct solution, or that the exercise is realistic
— human review and at least one other solver cover that for official packs. An LLM judging a challenge
correct counts as no evidence.
