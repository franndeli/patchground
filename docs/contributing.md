# Contributing challenges

Patchground challenges are plain committed files. Author them locally, validate them in Docker,
and let CI repeat the same validation on every change. For a first walkthrough see
[Author a first challenge](authoring.md).

## Author, validate, share

```sh
pgnd new my-challenge        # tiny working starter; no Docker needed
pgnd validate my-challenge   # builds and runs the verifier in Docker
pgnd show my-challenge
pgnd start my-challenge      # try the ticket in a separate session
```

Replace the starter as a unit: honest metadata and provenance, a realistic `TICKET.md`, a broken
`workspace/`, visible and hidden checks, a minimal `solution/reference.patch` and a pinned
`environment/Dockerfile`. To share several challenges, put them in a Git repository with a
`pack.yaml` and commit; others import committed files with `pgnd pack add`, then review the exact
version before its first build or run ([Pinned challenge packs](packs.md)).

## Test quality

- Hidden checks verify the ticket's stated behavior independently, never a hint about the fix.
- The reference patch fixes the application and must not edit tests.
- Use conventional pytest `test_*.py` / `*_test.py` modules with static test functions so the
  tampering probes apply. Inspect every gate: `not_run` is not a pass.
- Keep run-phase checks offline and deterministic.
- Correctness comes from tests only; there are no scores.

## Safe commits

- Commit `solution/` and hidden checks in the challenge source, but never copy them into the
  learner workspace or print them in logs, issues or pull requests.
- Never commit API keys, tokens, `.env` files, credentials, personal email addresses, phone numbers or
  home-directory paths. Use obviously fake values (`sk-test-not-a-real-key`).
- Do not bypass hooks or scans (`--no-verify`, forcing ignored files). Enable the repository
  hooks once per clone: `git config core.hooksPath .githooks`. Install `gitleaks` first and use a
  GitHub noreply commit identity; if a scan blocks a commit, stop rather than bypass it.
- `verification.json` is ignored local evidence, not portable proof; CI is the shared evidence.

## Validate changes in CI

Add the reusable Action to a workflow so pull requests re-run validation on changed or new
challenges: see [Validate challenges with the GitHub Action](validation-action.md). It needs an
explicit `allow-execution: "true"` and writes one JSON report. Configure the caller's job with a
read-only token and no secrets; the Action cannot enforce job permissions. Uploading the report
is an explicit choice in the caller's workflow.

Reviewers should read the Dockerfiles and checks of fork contributions before approving a run.
