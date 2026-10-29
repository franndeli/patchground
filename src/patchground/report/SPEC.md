---
id: patchground-report
type: module-design
status: draft
title: "Module: report"
parent: patchground-architecture
depends-on: [patchground-sessions, patchground-sandbox]
implements: [patchground-contract-feedback]
---

# report

Computes Part 1 of `patchground-contract-feedback` — the verified outcomes — from a session's event log,
its git data and container runs. Deterministic: the same session always yields the same report, and no
LLM is involved.

## Owns

- Each outcome as structured data (consumed by `cli` for rendering and `--json`, and by `ai` as
  evidence) plus the `report.md` rendering written into `.session/` on submit.
- **Regression test:** identify the user's new or changed test files from the diff against
  `original/`, run them in the sandbox against `original/` and against the final workspace; verified
  only if they fail before and pass after. Test-file detection uses language conventions (e.g.
  `test_*.py` / `*_test.py` for Python) *(unconfirmed)*.
- **Weakened tests:** removed test files, test functions or assertions, by comparing the original and
  final trees.
- **Diff scope** against `expected_paths`; **time and effort** from events.
- "Not established" as an explicit outcome state when evidence is missing — never a guess or a default
  pass.

## Boundary

Depends on `sessions` (records, events, git data) and `sandbox` (regression-test runs). Never imports
`ai`; never produces a score. mypy strict.
