# Patchground

*Real code. Real problems. Your tools.*

Open-source, local-first CLI (`patchground`, alias `pgnd`) for practicing real software engineering:
solve broken or incomplete repositories in your own editor, with your own AI (or none), and get
verified outcomes from checks that run in Docker.

Status: **early M1** — validate authored challenges and practice them locally with `start`, `check`
and `status`. Reset, doctor, challenge discovery and pack management are not implemented yet.

## Try a local challenge

Requirements: Python 3.12+, uv, Git and a running Docker engine. From this repository:

```sh
uv tool install .
pgnd start examples/pagination-last-page
```

Open the printed workspace in your editor. From that workspace:

```sh
pgnd status
pgnd check
# Edit the code, then run pgnd check again.
```

Outside a session directory, select it explicitly with `pgnd check --session <session-path>` or
`pgnd status --session <session-path>`. There is no implicit latest-session fallback. All commands
support `--json`; `start` also accepts `--no-timer`.

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
check does not silently rebuild or pull it.

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
