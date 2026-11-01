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
