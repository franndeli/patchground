# Patchground

*Real code. Real problems. Your tools.*

Open-source, local-first CLI (`patchground`, alias `pgnd`) for practicing real software engineering:
solve broken or incomplete repositories in your own editor, with your own AI (or none), and get
verified outcomes from checks that run in Docker.

Status: **local practice prototype** — create challenges with `new`, validate them,
discover them with `list` / `show`,
and practice with `start`, `check`, `status`, `hint`, `run` and `reset`.
Browse attempts with `sessions` and private checkpoints with `history`. `doctor` checks environment readiness.
Finish attempts with `submit` and read frozen verified outcomes with `report`.
The fresh-user usability trial is still pending; pack management is not implemented.

## Try a local challenge

Requirements: Python 3.12+, uv, Git and a running Docker engine. From this repository:

```sh
uv tool install .
pgnd doctor
pgnd list examples
pgnd show examples/pagination-last-page
pgnd start examples/pagination-last-page
```

Open the printed workspace in your editor. From that workspace:

```sh
pgnd status
pgnd check
# Edit the code, then run pgnd check again.
# To discard edits and try again:
pgnd reset
```

Outside a session directory, select it explicitly with `pgnd check --session <session-path>` or
`pgnd status --session <session-path>`. There is no implicit latest-session fallback. All commands
support `--json`; `start` also accepts `--no-timer` and `--no-history`. `reset --json` requires `--yes`.

`list [directory]` scans only immediate challenge folders (default: the current directory), with
`--type`, `--lang`, `--difficulty` and `--tag` filters. Invalid candidates are reported even when
filters are active. Discovery never builds, runs or grants trust; start still takes a local path.

Reset restores ordinary starting files and removes ordinary additions, but preserves `.git`,
credential-pattern entries (`.env*`, `*.pem`, `*.key`, `id_*`), the timer and event history. Stop
editors/agents from writing while resetting. Unsafe paths or protected-file collisions are rejected;
filesystem failure can leave a partial reset. Status keeps the last historical check; run a new check
for the restored workspace. There is no undo or automatic backup.

Doctor probes engine reachability/version, Git, and at least 1 GiB free on the session disk. It does
not measure the Docker VM disk or guarantee enough space for every image. It never builds or runs a
challenge. Follow its suggested fixes before starting.

See [the first-session guide](docs/first-session.md) for the full loop and troubleshooting.

Sessions live under `~/patchground/sessions/`. Each gets a new Git repository with an initial
baseline commit. Checks never change its HEAD, branches or staging area. The manifest and hidden
checks are frozen in private session metadata outside the editable workspace; removing the original
challenge folder does not break the attempt. The reference solution is never copied.

Image builds can use the network; checks run on an internal Docker network with resource limits.
Start validates structure and builds—it does not run the reference-validation gate. Use
`pgnd validate <challenge-path>` when authoring. Only start local challenges you authored or reviewed:
opening a workspace in your editor can execute project tooling outside Patchground's sandbox.

A check exits `0` only when it has tests and all pass, `1` for nonpassing results (including skipped
checks), and `2` for invalid input or infrastructure problems. Raw test output is never printed.
Status works without Docker. A removed session image must be restored or a new session started;
check does not silently rebuild or pull it. Multi-container services remain deferred; challenges
must use `environment.services: []`.

## Practice tools

```sh
pgnd hint
pgnd run -- python -m pytest tests/test_pagination.py
pgnd history
pgnd sessions
```

Hints come from frozen authored metadata; exhaustion succeeds without another event. `run` executes
literal arguments in a disposable container copy with no hidden checks and no host environment
forwarding. Container edits are discarded. It displays only a sanitized output tail (up to 64 KiB),
not verification evidence, and saves neither arguments nor output in session events. Put Patchground
options before `--`, for example `pgnd run --json -- python --version`. Use explicit `sh -c` only
when you want shell syntax inside the container.

New sessions capture initial and completed-check checkpoints in private session Git storage, never
in your branches or staging area. `start --no-history` opts out; older sessions are not migrated.
History skips credential patterns and Git-ignored files, and reports unavailable capture separately
from passing/failing tests. It is filtered history, not a complete replay of ignored files used by
checks or frozen submission evidence. `history` is read-only and remains available after submission;
periodic capture and snapshot restoration are not implemented. Reset still restores originals.
Unsupported or unsafe ignore contexts—including Git includes, linked-worktree metadata, relative
exclusion paths and unsupported Git environment overrides—make history unavailable rather than
silently retaining ignored files; checks remain usable.

## Finish an attempt

```sh
pgnd submit
pgnd report
# Outside the workspace:
pgnd report --session <session-path> --json
```

Submit captures the checked ordinary files, runs fresh checks and saves an immutable local report.
It can finalize a failed attempt (exit `1`); missing regression evidence is explicit, not a pass or
submission gate. Repeating submit returns the same result without rerunning. Further check/reset/hint/run
operations are rejected; start a new session to practice again. Your workspace remains editable,
but later edits cannot change the saved report. Report reads need no Docker.

For supported conventional pytest tests, regression evidence selects genuinely new/changed test
definitions and requires them to fail on original code and pass on final code. Pre-existing failures,
skips, missing tests, collection problems and unsupported/changed harnesses do not count as proof.
The report also records changed checked files (including ordinary Git-ignored files), expected-path
scope, structural test removals, elapsed time and practice-check/hint counts. Binary/non-UTF-8 or
over-1-MiB line counts are unestablished. Assertion-count reductions are facts, not judgments about
semantic test strength. There is no overall score or AI judgment.

Infrastructure errors before finalization leave the attempt open. If a failure occurs after the
bundle is published, retry submit to verify/reconcile it rather than assuming rollback. This is
local evidence, not tamper-proof attestation. See [the feedback contract](docs/contracts/feedback.md).

## Author a challenge

```sh
pgnd new my-challenge
pgnd validate my-challenge
```

`new` defaults to `--type debug --lang python` and creates a runnable teaching starter in the
current directory. It refuses any existing destination and never builds or runs automatically.
Only that template combination is currently supported. The starter includes an intentional defect,
checks and a reference patch; replace them together rather than changing only the ticket.
See [the authoring guide](docs/authoring.md) for the full workflow and safety limits.

The curated examples cover pagination, duplicate charges on retry, and cache expiry. They are
Docker-validated, not yet human-rated for difficulty or realism.

## Validate an authored challenge

`pgnd validate <path>` builds once, proves the broken state fails and the reference passes, then
checks determinism across three runs each of visible-only, combined and reference checks (nine
check containers for this part). Test IDs, statuses, occurrence counts and outcomes must agree; ordering
and timing may differ. A mismatch fails at `determinism`. Only structured results are reported.

Success writes a local `verification.json`; failure removes an earlier Patchground record.
Use `--no-write` for read-only validation. Three stable runs are bounded evidence, not a guarantee
that a challenge can never be flaky.

For supported Python/pytest layouts, `anti_gaming` then probes an empty diff, deletion of editable
test modules, and skipping those modules (three more containers, twelve total). Hidden test IDs,
counts and statuses must match the broken baseline exactly. Mutations use disposable copies and
never change authored files or hidden checks. Conventional `test_*.py` / `*_test.py` modules with
static `test_*` functions or methods in `Test*` classes are supported; helper-only modules are kept.

Other runners/layouts, absent editable tests, or ineffective mutations are explicitly `not_run`,
not passed. A `valid` result means all executed gates passed: inspect step statuses before claiming
anti-gaming coverage. This bounded probe does not prevent malicious test runners, forged results,
custom discovery/plugin bypasses or local cheating.

## Website

The product homepage lives in [`web/`](web/README.md). Preview it locally with
`npm --prefix web run dev`, then open `http://127.0.0.1:4173`. It introduces the CLI, local practice
workflow and real challenges, with contribution as a secondary path. It does not host execution.
See the web README for checks, the static build, and the separate deployment approval gate.

## Develop

```sh
uv sync
uv run pgnd validate examples/pagination-last-page
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest                 # Docker tests are skipped if no engine is reachable
PATCHGROUND_REQUIRE_DOCKER=1 uv run pytest -m docker  # require integration tests to run
```

One-time setup per clone: `brew install gitleaks && git config core.hooksPath .githooks`.

Specs: `goal-and-requirements.md`, `architecture.md`, `docs/contracts/`, `src/patchground/*/SPEC.md`.

## License

Apache-2.0 for the CLI. Each challenge declares its own `content_license`.
