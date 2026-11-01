# Contributing to Patchground

Thanks for helping. There are two ways to contribute.

## Improve the CLI

```sh
git clone https://github.com/franndeli/patchground && cd patchground
uv sync
git config core.hooksPath .githooks          # needs gitleaks: brew install gitleaks
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest                                 # Docker tests are skipped without an engine
```

- Read the `SPEC.md` of the module you change and the contracts in `docs/contracts/` it implements.
  A change that alters a boundary or contract updates the owning spec in the same pull request.
- Challenge commands only ever run in containers. Never print hidden checks or copy `solution/` into
  a workspace.
- Use obviously fake values in tests (`sk-test-not-a-real-key`). Never commit secrets or personal
  data.
- Keep pull requests small, with tests for new behaviour.

## Write a challenge

See [docs/contributing.md](../docs/contributing.md) and the
[authoring guide](../docs/authoring.md). `pgnd new` creates a runnable starter, and `pgnd validate`
proves it in Docker.

## Report a problem

Open an issue using one of the templates. For security problems, follow [SECURITY.md](SECURITY.md)
instead of opening a public issue.
