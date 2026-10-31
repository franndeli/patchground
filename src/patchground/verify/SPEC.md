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
challenge folder except to write `verification.json`, or to delete a stale Patchground one when
validation fails. mypy strict.

## Implementation notes

- Entry point: `validate_challenge(folder, *, limits, write, sandbox, progress) -> ValidationReport`.
  Steps `manifest`, `build`, `broken_fails`, `reference_passes`, `determinism` run fail-fast;
  `anti_gaming` remains `not_run`. Determinism reuses the first three summaries as its baselines,
  then compares repeats as specified by the verification contract. Reference-copy preparation is
  shared so repeat runs retain the same patch safety and cleanup guarantees. Non-empty
  `environment.services` fails
  `manifest` (multi-container services are deferred beyond the single-container prototype).
- Host problems (engine unreachable, engine errors, git missing, a temp folder or workspace copy
  that fails, a `verification.json` that can't be written or removed) raise
  `VerifyEnvironmentError`; they are not step failures. Challenge problems the sandbox would reject (symlinks, layer clashes,
  e.g. a reference patch creating a check file) are checked first and fail the step.
- `reference.patch` is applied with host `git apply -p1` (`--check` first, never `--unsafe-paths`)
  to a copy of `workspace/` in the system temp dir; a patch that changes no file fails the step.
  Git must never read configuration a challenge supplies, because a repo-local filter runs host
  commands: the copy drops every `.git` entry (any case, any depth), and git runs with `GIT_DIR`
  set to a fresh empty bare repo beside the copy and `GIT_WORK_TREE` set to the copy, so no
  repository is discovered. On top: no system/global config or attributes, hooks and fsmonitor off,
  `GIT_CEILING_DIRECTORIES`, a minimal environment.
- Test-id integrity: step 2 is inconclusive if a visible test from the first run is missing from the
  second, and step 3 requires every id seen in step 2.
- Run logs are never surfaced: a run that includes hidden checks may print their source. Step
  details carry test ids, statuses and counts only.
- `verification.json` (written atomically, only when every executed step passed; on failure an
  existing file is deleted only if it is a Patchground record and the folder has `challenge.yaml`):
  `{format: "patchground-verification", format_version: 1, patchground_version,
  challenge: {id, version, spec_version}, image_id, validated_at, steps: [{name, status, detail,
  started_at, finished_at, runs: [{label, outcome, counts, tests: [{id, status}]}]}]}`. Never file
  contents, the patch, or run logs. `read_verification` returns `None` for a missing or unusable
  file. Digest-mismatch re-validation is deferred.
