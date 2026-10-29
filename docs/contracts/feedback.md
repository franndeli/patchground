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
| Checks passed | Per-test results of the last check, e.g. 12/12. |
| Regression test | The user's new or changed tests run against the pristine original workspace: verified only if they fail there and pass on the final workspace. |
| Tests deleted or weakened | Removed test files, functions or assertions are flagged. |
| Diff scope | Files and lines changed; files outside `expected_paths`, if declared. |
| Time and effort | Total time vs timebox, number of checks, hints used. |

Each outcome is stated as a fact ("Verified: fails before, passes after"), never as a grade. When an
outcome cannot be established it says so, rather than guessing.

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
