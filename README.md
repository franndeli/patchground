# Patchground

*Real code. Real problems. Your tools.*

Open-source, local-first CLI (`patchground`, alias `pgnd`) for practicing real software engineering:
solve broken or incomplete repositories in your own editor, with your own AI (or none), and get
verified outcomes from checks that run in Docker.

Status: **M1 local prototype** — validate authored challenges, discover them with `list` / `show`,
and practice with `start`, `check`, `status` and `reset`. `doctor` checks environment readiness.
The fresh-user usability trial is still pending; pack management and reports are not implemented.

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
support `--json`; `start` also accepts `--no-timer`. `reset --json` requires `--yes`.

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
must use `environment.services: []`. A passing check is the current end of an attempt—`submit` and
verified-outcomes reports arrive later.

## Validate an authored challenge

`pgnd validate <path>` builds once, proves the broken state fails and the reference passes, then
checks determinism across three runs each of visible-only, combined and reference checks (nine
check containers total). Test IDs, statuses, occurrence counts and outcomes must agree; ordering
and timing may differ. A mismatch fails at `determinism`. Only structured results are reported.

Success writes a local `verification.json`; failure removes an earlier Patchground record.
Use `--no-write` for read-only validation. Three stable runs are bounded evidence, not a guarantee
that a challenge can never be flaky. Anti-gaming validation remains explicitly `not_run`.

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
