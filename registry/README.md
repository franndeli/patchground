# Community pack registry

The public index of community challenge packs. Content lives in authors' repositories; this folder
holds only the discovery/validation script and its two generated outputs. Design and guarantees:
`SPEC.md`.

## For authors: publish and appear

1. `pgnd new my-bug` → `pgnd validate my-bug` until it is *valid*.
2. Put the challenge folder(s) at the root of a public repository next to a `pack.yaml`
   (`spec_version`, `name`, `version`, `description`, `challenges: [...]`). Declare
   `content_license` and `provenance` in each `challenge.yaml`; keep `services: []`.
3. Add the GitHub topic **`patchground-pack`** to the repository. Other hosts: add the `https://`
   clone URL to `sources.yaml` here.
4. Within a few hours the registry clones the repository, re-runs `pgnd validate` on every
   challenge and publishes the result. Verified packs appear on the site; anything else is listed on
   the status page with the failing step.

No pull request, no account, no review queue. The validator is the gate.

## Files

- `crawl.py` — discovery → clone → policy → `pgnd validate` → `index.json` / `status.json`.
- `sources.yaml` — manual list of public git URLs for hosts without topic search.
- `index.json` — verified packs with public metadata only. **Written by CI.**
- `status.json` — every source seen, with result and failing step. **Written by CI.**

## Running locally

```sh
uv run python registry/crawl.py --dry-run                       # discovery + policy, no Docker
uv run python registry/crawl.py --source https://github.com/x/y.git   # one pack, full validation
PG_REGISTRY_ALLOW_FILE=1 uv run python registry/crawl.py --source file:///tmp/my-pack  # tests only
```

A full run needs Docker and `gitleaks` on PATH (the secret scan is skipped with a warning
otherwise). Do not commit locally generated `index.json`/`status.json`; CI owns them.

## Workflow

`.github/workflows/registry.yml` runs every six hours and on demand. The `validate` job has a
read-only token and no secrets because it builds untrusted Dockerfiles; the `publish` job commits
the outputs and the regenerated site catalog only if they changed.
