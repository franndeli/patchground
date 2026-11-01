---
id: patchground-contract-feedback
type: architecture-design
status: draft
title: "Contract: feedback"
parent: patchground-architecture
depends-on: [patchground-contract-execution]
---

# Feedback

A report has two parts that are never mixed: facts Patchground can verify, then coaching it can only
offer. There is no overall score. Git history cannot tell careful investigation from pasting an
agent's answer, so the report never claims to.

## Part 1: verified outcomes (deterministic, no AI)

| Outcome | How it is established |
| --- | --- |
| Checks passed | Fresh per-test results from the captured submission input, e.g. 12/12; never a stale historical check. |
| Regression test | The user's new or changed tests run against the pristine original workspace: verified only if they fail there and pass on the final workspace. |
| Test structure | Conventional test-file/function removals and assertion-count decreases are flagged as structural facts, not semantic weakness. |
| Diff scope | Files and lines changed; files outside `expected_paths`, if declared. |
| Time and effort | Time at submission request vs timebox (or timer off), practice checks and hints used; verification probes are separate. |

Each outcome is stated as a fact ("Verified: fails before, passes after"), never as a grade. When an
outcome cannot be established it says so, rather than guessing.

### Finalization and evidence limits

Submission freezes the checked ordinary files and runs fresh verification. One complete private
bundle commits the final report. Repeated submit returns it unchanged; later workspace edits do
not alter evidence. Submitted sessions reject further practice mutations; start a new session.
Failing checks may finalize (submit exits `1`). Missing, unsupported or unsuccessful regression
evidence is reported, not treated as a pass or a submission gate. Infrastructure failure before
commit leaves the attempt open; after publication, retry reconciles the audit without reopening.

Regression adapters support conventional static pytest definitions and the bounded TypeScript
subset in `patchground-contract-verification`. They select genuinely
new/changed tests and compares exact identities/multiplicities on original and final code; unrelated
pre-existing failures, collection errors, missing/skipped tests and changed test harnesses cannot
establish a regression. Only individual before-failing/after-passing identities are verified.
Vitest selection requires exact file/name identities and identical selected final test material in
both disposable trees, frozen imports/helpers and unchanged harness/dependency files. Deleted final
test modules are never restored. Source parsing is bounded at 1 MiB/module and selection at 200
candidates. Unsupported syntax or harness ambiguity is explicitly `not_established`.
This is bounded evidence, not protection against malicious local forgery or an arbitrary plugin.

Scope includes ordinary Git-ignored files because they were checked. Sensitive patterns and Git
metadata are excluded. Binary, non-UTF-8 or over-1-MiB file line counts are explicitly unestablished.
Expected paths are literal paths/directory prefixes. Structural assertion counts cannot judge the
strength of equivalent rewrites or prove all possible test weakening.

`report` reads saved structured/Markdown evidence without Docker; active sessions have no final
report. Core outcomes never depend on AI, attached transcripts or source-checkout availability.

## Part 2: coaching (optional, AI, experimental)

`pgnd debrief --ai` reads the ticket, `questions.md`, the verified outcomes, the final diff and the
check history, then interviews (3–6 adaptive questions, one at a time), observes each `focus` area,
and suggests 2–3 improvements and next challenges.

Guardrails:

- Part 1 outcomes cannot be overridden by the model.
- Every observation cites evidence (file and line, check number, or an answer); one without evidence
  is rejected and regenerated. Without evidence the area reads **"Not observed"** — e.g. AI usage is
  not observed unless a transcript was attached with `submit --transcript`.
- Low temperature; structured output validated, retried at most twice, then a clear failure.
- The full prompt and context are saved in `.session/` for inspection.

The coaching part stays in the product only if users of real sessions find its questions realistic and
instructive.

## Example

```
duplicate-charges-on-retry · 38 min of 45 · 4 checks · 1 hint

VERIFIED
  Checks             12/12 passing
  Regression test    Verified: fails before, passes after
  Diff scope         2 files, +41 −6, all inside src/payments/

COACHING (AI, optional)
  Debugging method   Reproduced the timeout before changing code (check #1 red on the new test)
  AI usage           Not observed: no transcript provided
```
