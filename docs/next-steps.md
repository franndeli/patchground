# Project health and next sessions

Baseline: the 0.2.0 release commit on `main` (architecture practice, see the changelog). This is a
resume index, not a security audit or publication approval. Recheck live state when resuming. For
the daily routine, see [maintenance](maintenance.md).

## Current state

- **PyPI:** 0.1.0 is published. 0.2.0 is tagged and published only after the owner approves the
  `release` and `pypi` environments in the release workflow (see [publishing](publishing.md)).
  Recheck PyPI before assuming either.
- **Catalog:** source contains eighteen built-in challenges: debug, feature and architecture work
  in Python and TypeScript. The site and `catalog.json` are generated from `examples/` at build time;
  the live site showed all fifteen pre-architecture challenges on 2026-11-07. Counts are never
  written by hand (tests reject them in the landing and README).
- **Architecture practice:** the `architecture` challenge type (contract:
  [challenge format](contracts/challenge-format.md)) and three new challenges,
  `sales-report-layers`, `shipping-carrier-plugins` and `payment-vendor-boundary`, plus the
  retyped `order-notifications-boundary`. Each passed all six `pgnd validate` steps and the
  installed-wheel release-candidate check. An independent review found loopholes and unstated
  requirements; they were fixed and the bypasses were re-run in real sessions to confirm they fail.
- **Website:** the challenge list shows five per page with Previous/Next; filters and search span
  the whole catalog. Without JavaScript every challenge is listed.
- **CI:** green on `7c673bb` (core, web, validation Action, secret scan) and on the scheduled
  registry runs. Check the current commit before relying on it.
- Independent-human learner and author acceptance remains **pending recruitment**. Synthetic runs
  do not establish it.

## Completed follow-up

See [the evaluation](evaluations/agent-guide-smoke.md),
[structured evidence](evaluations/guidance-trial-evidence.json), and
[predeclared protocol](evaluations/guidance-trial-protocol.md).

- Corrected four-starter and challenge-reference guidance, Workers deployment instructions, and
  published-versus-deferred status. Owning goal, architecture, CLI, web, and contract specs now separate
  shipped behavior from AI/configuration/registry-helper plans. Historical failures remain recorded.
- Added guidance checks with deliberately broken fixtures and real scaffold/discovery exercises.
  The README skill-copy procedure is tested to refuse an existing destination.
- Fresh synthetic learner and author roles completed Docker-backed sessions against published 0.1.0.
  Final results were 13 and 11 passing checks respectively, both with verified regression evidence.
  The coordinator reread both reports and reran the authored challenge's six-step validation.
- A synthetic guide produced eight replies covering seven scenario groups and fetched the exact
  public skill. Unsafe scenarios were response-only, not proof of execution refusal.
- Fixed the start argument's missing built-in-ID description and an observed 320px illustrated-report
  overflow. Browser smoke proves clipboard write/readback, keyboard navigation, graceful failure,
  no-script availability, and narrow layouts. Its new CI job still needs an observed run after push.
- A separately built final wheel passed clean Python 3.12 installation/scaffold/discovery/help checks
  outside the checkout, without Anthropic installed. It was not substituted into the published-package
  trials or published as a release.

The completed documentation-parity and guide-validation task specs are retired; their durable
requirements and evidence live in the owning specs, tests, and evaluation above.

## Next priority: independent-human acceptance

Spec: [Human acceptance](work/human-acceptance.md).

The owner needs to arrange one unfamiliar learner and one independent author. Use the existing
[trial kit](evaluations/human-trial-kit.md), which now starts from the installed built-in catalog,
and [findings record](evaluations/human-trial-findings.md). Record actual versions, assistance,
failures, and unfinished attempts. A participant's usual AI is allowed; identify whether they use
the guide. Do not replace this work with another synthetic cohort.

No new feature work is required to begin recruitment. If participants remain unavailable, keep
this gate pending rather than inventing observations or marking it passed.

## Later, only when evidence justifies it

- Platform coverage: existing CI covers Ubuntu/Python 3.12 with Docker; local wheel evidence covers
  macOS. WSL2, Podman, and cold-cache installation are not established by this follow-up.
- Content: three beginner challenges and four architecture challenges exist. Difficulty and timeboxes
  remain author estimates. Calibrate the expanded catalog with human feedback before claiming
  interview fidelity, usefulness, or measured completion times.
- Registry-name installation and a publish helper remain planned, not practice prerequisites.
- Systems practice beyond one process (multi-container `services`) needs a runner and sandbox
  redesign with a security review. Written design challenges (`design`) stay reserved because
  tests cannot verify them.
- AI coaching/generation, stages, multi-container services, periodic history capture, and restoration
  remain deferred. No accounts, hosted execution, or overall scoring.
- Any future package release or production deployment needs separate explicit approval. The help
  wording fix and responsive layout fix are not yet evidence of changed published behavior.

## Verification context

The [guidance evaluation](evaluations/agent-guide-smoke.md) and
[interview batch evaluation](evaluations/interview-batch.md) name separate artifacts and checks.
The earlier guidance follow-up did not rerun the full Docker suite. The batch record includes its
own full-suite attempts, the pre-existing sandbox residue they exposed, and subsequent verification.
Do not substitute old results for the current candidate or imply that local checks establish CI.

Historical baseline CI was green:
[core](https://github.com/franndeli/patchground/actions/runs/41630504321),
[web](https://github.com/franndeli/patchground/actions/runs/41630504431),
[secret scan](https://github.com/franndeli/patchground/actions/runs/41630504348),
[validation Action](https://github.com/franndeli/patchground/actions/runs/41630504341), and
[registry](https://github.com/franndeli/patchground/actions/runs/41650557242).
These results do not establish CI for the follow-up changes.

## Resume

1. Read this index, the remaining task spec, and its owning contracts.
2. Check branch/worktree state, published version, and current-commit CI. Do not treat historical
   evidence as live state or silently publish local changes.
3. Confirm participant availability and track the selected work in the shared TODO plan.
4. For a new behavior change, agree the design and update its owning spec; existing tasks do not
   authorize purchases, infrastructure changes, or publication.
5. Record observed results and remaining blockers. Retire the human task only after the agreed
   acceptance work is complete.

Historical delivery evidence remains in [the delivery ledger](delivery-plan.md).
