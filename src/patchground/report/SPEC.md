---
id: patchground-report
type: module-design
status: draft
title: "Module: report"
parent: patchground-architecture
depends-on: [patchground-sessions, patchground-sandbox, patchground-verify]
implements: [patchground-contract-feedback]
---

# report

Computes Part 1 of `patchground-contract-feedback` from captured ordinary files, session events and
container runs. `submit_session` orchestrates the session-owned snapshot/commit API; `saved_report`
reads the immutable result without Docker. Repeated submission returns the same saved evidence,
not a new observation of the live workspace. No LLM is involved.

## Owns

- Versioned, round-trippable outcome data plus deterministic Markdown stored in the session-owned
  `.session/submission/` bundle. The bundle, not a last historical check or live Git state, supplies
  final evidence. Final checks are fresh; unsupported/missing regression evidence never blocks
  submission or silently passes. Failing checks may finalize an unsuccessful attempt.
- **Regression test:** select actual new/changed conventional pytest definitions and run identical
  candidate material on disposable original/final-code copies. Only identities failing before and
  passing after are verified; unchanged pre-existing failures cannot establish a regression. Require
  matching identities/multiplicities, successful final runner outcome and every selected final test
  passing. Known negative evidence (including no new tests or skipped/errored collection) is
  `not_verified`; unsupported/inconclusive evidence is `not_established`. Neither counts as proof.
  Select at most 200 definitions, parsing at most 1 MiB per module; reject identities that would
  require display truncation/sanitization. Frozen `testpaths` is compatible with explicit candidate
  selection; changed runner configuration, collection controls and ambiguous helper changes are not.
- **Test structure:** conventional test-file/function removals and decreases in AST assertion counts.
  These are structural facts, never proof that an equivalent rewrite is semantically weaker.
- **Diff scope:** captured ordinary files versus original, including Git-ignored ordinary files but
  excluding Git and credential patterns. Expected paths are literal file/directory prefixes, not
  globs. Stream hashes for change detection; line counts are unestablished for binary/non-UTF-8 files
  or files above 1 MiB. Executable-bit changes also count as file changes.
- **Time and effort:** elapsed time at the submission request (unestablished with timer off), practice
  check count and hints revealed. Submission/regression verification is not counted as practice.
- "Not established" as an explicit outcome state when evidence is missing — never a guess or a default
  pass.

## Boundary

Depends on `sessions` for captures, persistence and lifecycle, `sandbox` for regression runs and
`verify` for shared pure pytest/static-analysis helpers. Never shells out to Git, imports AI or
produces a score. Engine/storage faults before finalization remain retryable; an already published
bundle is never reopened after an audit failure. mypy strict.
