# Patchground

*Real code. Real problems. Your tools.*

Open-source, local-first CLI (`patchground`, alias `pgnd`) for practicing real software engineering:
solve broken or incomplete repositories in your own editor, with your own AI (or none), and get
verified outcomes from checks that run in Docker.

Status: **M0** — the challenge format v0.1 and `pgnd validate`. Nothing is playable yet.

## Develop

```sh
uv sync
uv run pgnd validate examples/<challenge>
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest                 # Docker tests are skipped if no engine is reachable
uv run pytest -m docker       # integration tests only
```

One-time setup per clone: `brew install gitleaks && git config core.hooksPath .githooks`.

Specs: `goal-and-requirements.md`, `architecture.md`, `docs/contracts/`, `src/patchground/*/SPEC.md`.

## License

Apache-2.0 for the CLI. Each challenge declares its own `content_license`.
