# Changelog

All notable changes to the Patchground CLI. The format follows Keep a Changelog; versions follow
Semantic Versioning. Before 1.0, minor versions may change the CLI and challenge format.

## [0.1.0]

First public preview. Local-first: no account, no hosted execution, no built-in AI, no overall score.

### Added

- Sessions: `start`, `check`, `status`, `reset`, `hint`, `run` (disposable diagnostic container),
  `sessions`, `history` (private checkpoints that never touch your Git state).
- `submit` and `report`: an immutable, test-backed debrief — check outcomes, regression evidence
  (your test fails on the original code and passes on yours), diff scope and structural test
  observations. Unsupported evidence is reported as such, never as a pass.
- Six curated challenges across Python and TypeScript, debugging and feature work, bundled with the
  CLI: `pgnd list --builtin`, then `pgnd start <id>`. No checkout is needed.
- `PATCHGROUND_SESSIONS_DIR` keeps sessions somewhere other than `~/patchground/sessions`.
- Authoring: `new` with four starters (Python/TypeScript × debug/feature) and `validate`, which proves
  in Docker that the broken state fails, the reference passes, results are stable and editable-test
  shortcuts are caught where supported.
- Pinned challenge packs from public Git repositories, with an explicit consent review before anything
  builds or runs.
- A reusable GitHub Action that validates committed challenges.
- `doctor`, `list`, `show`; every command supports `--json`. An empty `list` and `start` print the
  next commands to run.

### Fixed

- Terminal `submit` and `report` output no longer shows Markdown escapes such as `test\_name`.

- Checkpoint history no longer reports "unavailable" in editor and agent terminals that export
  `GIT_ASKPASS` or credential settings through `GIT_CONFIG_COUNT`.

### Known limitations

- Checks need Docker (or Podman); Windows through WSL2 only.
- TypeScript checks establish runtime behavior, not static type correctness; regression and test-structure
  evidence covers a bounded subset of Vitest syntax.
- Multi-container challenges (`environment.services`) are not supported.
- Optional AI coaching and challenge generation are deferred and not included.
- Some container engines occasionally lose out-of-memory reports; such a kill is shown as exit 137
  without a memory label rather than guessed.
