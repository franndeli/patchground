---
id: patchground-verify
type: module-design
status: draft
title: "Module: verify"
parent: patchground-architecture
depends-on: [patchground-spec, patchground-sandbox, patchground-packs, patchground-safeio, patchground-runner-assets]
implements: [patchground-contract-verification]
---

# verify

Runs `patchground-contract-verification` against a challenge folder and produces `verification.json`.
One implementation serves `pgnd validate`, the in-repository validation Action in CI, and the generator, so a
challenge passes or fails the same way everywhere.

## Owns

- The ordered steps and fail-fast semantics; a structured result naming the failed step and why.
- Building the workspace variants the steps need, all in temporary copies: the starting state, the
  reference applied, and the anti-gaming variants (empty diff, editable supported test modules deleted
  or skipped with hidden checks untouched).
- Determinism: repeat runs and compare per-test outcomes, not just pass/fail totals.
- Writing and reading `verification.json`, and detecting a digest mismatch that requires re-validation.

## Boundary

Depends on `spec`, `sandbox`, packs preparation and shared `safeio`; never on `sessions`.
Installed validation first enforces exact-version consent and works on a disposable verified copy;
its report uses canonical paths and never writes or deletes cache verification records. Local
validation may write `verification.json` or delete a stale Patchground record on failure. mypy strict.

## Implementation notes

- Entry point: `validate_challenge(folder, *, limits, write, sandbox, progress, input_roots, ...) -> ValidationReport`.
  Callers validating captured input supply its original/captured roots through `input_roots`; these
  augment, never replace, pack preparation's mandatory Git executable exclusions. Automation uses
  `write=False`, retaining no verification record in the checkout.
  All six steps run fail-fast; unsupported anti-gaming adapters/layouts remain explicitly `not_run`.
  The bounded pytest adapter recognizes direct invocations and static conventional test definitions
  in safety-checked temporary editable-layer copies, preserving helper-only modules even with test
  filenames. It appends skip marks without importing code
  on the host. Observable mutation effects are required before claiming resistance. Hidden outcomes
  must exactly match the broken baseline as defined by the verification contract.
  Determinism reuses the first three summaries as its baselines,
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
- Pytest recognition lives in `verify/pytest_adapter.py`, a pure module (tokenising and `ast`
  only; it never executes authored code): direct `pytest` / `python -m pytest` command splitting,
  conventional test filenames, and static `test_*` functions and `TestC::test_*` methods
  (`test_definitions(path)` bounds source at 1 MiB and raises `UnsupportedPytest`, without source
  text, for unparsable, oversized or duplicate-named tests). The tampering
  probes and `report`'s regression evidence share the same basic syntax rules; regression adds
  size/ambiguity bounds, while `tampering` keeps its public names and behaviour.
- TypeScript recognition uses the shared inert Tree-sitter adapter and exact canonical Vitest
  command from `patchground-runner-assets`. Only conventional `.test.ts` modules with canonical
  named imports and standalone unique literal test calls are supported; suites, hooks, aliases,
  modifiers, dynamic registration and ambiguous identities decline additional evidence. Parsing is
  bounded at 1 MiB/module. Actual editable collection must exactly match static file/name identities
  before tampering; `.git` and `node_modules` are excluded. No authored code runs on the host.
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
