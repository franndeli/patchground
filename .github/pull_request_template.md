## Summary

<!-- What changes and why. Link the issue: Closes #NNN -->

## Checklist

- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy`
- [ ] `uv run pytest` (and `-m docker` if the sandbox, sessions or verify changed)
- [ ] The owning `SPEC.md` or contract is updated if a boundary or contract changed
- [ ] No secrets, personal data or hidden-check content
