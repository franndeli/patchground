---
id: patchground-verify
type: module-design
status: draft
title: "Module: verify"
parent: patchground-architecture
depends-on: [patchground-spec, patchground-sandbox]
implements: [patchground-contract-verification]
---

# verify

Runs `patchground-contract-verification` against a challenge folder and produces `verification.json`.
One implementation serves `pgnd validate`, the `validate-action` in CI, and the generator, so a
challenge passes or fails the same way everywhere.

## Owns

- The ordered steps and fail-fast semantics; a structured result naming the failed step and why.
- Building the workspace variants the steps need, all in temporary copies: the starting state, the
  reference applied, and the anti-gaming variants (empty diff, failing tests deleted or skipped).
- Determinism: repeat runs and compare per-test outcomes, not just pass/fail totals.
- Writing and reading `verification.json`, and detecting a digest mismatch that requires re-validation.

## Boundary

Depends on `spec` and `sandbox`; never on `sessions` (validation has no session). Never modifies the
challenge folder except to write `verification.json`. mypy strict.
