# Daily maintenance

A routine for keeping Patchground healthy with one small, verified improvement a day. Current state
and priorities live in [next steps](next-steps.md); this page is the habit, not the backlog.

## Every day (about 5 minutes)

1. Check health, and fix anything red before starting new work:

   ```sh
   gh run list --limit 10            # core, web, validation Action, secret scan, registry
   gh issue list && gh pr list
   curl -s https://pypi.org/pypi/patchground/json | python3 -c "import json,sys;print(json.load(sys.stdin)['info']['version'])"
   curl -s https://patchground.dev/catalog.json | python3 -c "import json,sys;print(len(json.load(sys.stdin)['challenges']))"
   ```

   The site count should equal the number of folders under `examples/` once `main` is deployed.
2. Pick **one** item from the backlog below and finish it.
3. Before committing: `uv run ruff check src tests`, `uv run mypy src`, `uv run pytest -q -m "not docker"`,
   `npm --prefix web test`, and `uv run pgnd validate examples/<id>` for any challenge you touched.
   Run the `deslop` skill on the diff, then push.

## Backlog kinds

- **Content:** one new challenge or a fix to an existing one. Write the ticket so that every hidden
  check is satisfiable from it alone, then validate it in Docker. Try a deliberately wrong
  "solution" in a real session (`pgnd start`, edit, `pgnd check`) to confirm the hidden
  checks catch it.
- **Quality:** one flaky test, unclear error message or confusing help text.
- **Docs:** keep [next steps](next-steps.md) and the README in line with what is live. Do not
  write counts of challenges by hand; tests reject them.
- **Feedback:** triage issues from people who used a challenge; difficulty and timeboxes are
  author estimates until humans rate them.

## Every week

- Collect merged changes into a release candidate: bump `pyproject.toml`, update `CHANGELOG.md`,
  and run `bash docs/evaluations/release-candidate-check.sh` with Docker up.
- Run the `thermos` review (or an independent reviewer) on the changes since the last tag.
- Publish only with the owner's approval, following [publishing](publishing.md).
