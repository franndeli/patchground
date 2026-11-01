# CLI artifact review — not a published release

## Prepared artifacts

Wheel and source distribution were built from committed source
`7097b368a2b8e53529d7b86d9863c864383ad218`, excluding all uncommitted website/registry work.
The existing version remains **0.0.1**; no version bump or publication is implied.

The [artifact manifest](cli-artifact-manifest.json) records filenames, byte sizes and SHA-256 digests.
Artifacts are retained locally, not uploaded. Rebuilding the wheel from the source distribution
produced byte-for-byte identical wheel contents and archive bytes in this environment.

## Verification

- Fresh Python 3.12 core-only installation, without Anthropic or LiteLLM.
- All four Python/TypeScript × debug/feature starters passed all six Docker validation gates.
- Installed-wheel TypeScript submission established a before-fail/after-pass regression while
  preserving learner Git bytes.
- Saved report and repeated submission remained identical after live workspace edits, with the
  sandbox execution entry point patched to fail if called.
- Installed CLI help/version worked; the deferred AI coaching command and modules were absent.
- Source commit CI `41318435188`, validation Action smoke `41318435091` and secret scan
  `41318435152` all completed successfully.
- Runtime code, tests and dependencies are unchanged from the frozen ten-learner candidate `44da6dd`.
  The restored core previously passed 1,104 Docker-required tests; targeted adapter/report acceptance
  subsequently passed 113 tests. See the [cohort evidence](learner-cohort.md).

An initial packaging-harness assertion incorrectly assumed version 0.1.0. It was corrected to read
the committed version, and the entire artifact build/install/smoke was rerun successfully. The
product's version behavior was correct and was not changed.

## Open gates before publication

- **Independent-human onboarding:** an unfamiliar person follows the
  [fresh-user checklist](../first-session.md#fresh-user-acceptance-checklist) without maintainer help.
  Ten synthetic completions do not satisfy this gate.
- **Independent authoring:** a person authors and solves from the
  [authoring guide](../authoring.md), with usability/content findings recorded separately.
- **Website handoff:** its separate owner supplies reviewed, verified documentation/catalog artifacts.
  This CLI candidate does not include, deploy or attest that work.
- **Publication decisions:** confirm the intended package/release version, publisher identity and
  hosting/DNS prerequisites. Request explicit approval at the actual package publication, release,
  DNS or production-deployment action; no standing approval is assumed.
- **Known limits:** optional AI coaching/generation are deferred; bounded TypeScript structural evidence
  does not support every runtime assertion form; the earlier intermittent Docker OOM-classification
  observation remains unreproduced, not declared fixed.

The owner has since chosen version **0.1.0**, Cloudflare Pages for the site and PyPI trusted
publishing. The version is bumped and the release workflow (`.github/workflows/release.yml`) rebuilds
and re-verifies the distributions from the tagged commit, so the 0.0.1 files above are superseded
evidence, not the artifacts that will ship. See [the publishing runbook](../publishing.md).

The CLI artifacts are ready for review. These remaining gates prevent a claim that the full public
product is accepted or launched.

## 0.1.0 candidate, 2026-11-01

Run after the fresh-user trials, the built-in catalog and the seventh (refactor) challenge, on
macOS with Docker 28.5.2, Python 3.12.

- `docs/evaluations/release-candidate-check.sh` passed: through an installed wheel in a fresh
  virtual environment with its own sessions directory, every built-in challenge (7) went through
  show, start, failing check, status, hint, reference patch, passing check, available history,
  passing submit, report, post-submit rejection and listing; reset restored a workspace; the four
  `new` starters validated; a local pack was added, refused without consent, started with `--yes`,
  listed and removed.
- Full suite: 1,021 non-Docker and 103 Docker tests passed; ruff, mypy and the schema export are
  clean; `twine check` passes on the wheel and sdist.
- Publication readiness: the PyPI name `patchground` is unclaimed (`/simple/patchground/` → 404).
  `release.yml` publishes through the `pypi` environment (owner `franndeli`, repository
  `patchground`, workflow `release.yml`), which matches the pending trusted publisher the owner
  registered. Whether that registration exists can only be seen from the owner's PyPI account;
  the first tagged release is the only end-to-end proof. Both the `release` and `pypi` GitHub
  environments require the owner's approval and accept only `v*` tags. An earlier environment named
  `papi` would not have gated the upload; it was replaced.
- Not covered: Linux and WSL2 hosts, Podman, a cold Docker image cache, and any human session.
