# Project health and next sessions

Baseline: `01c399afe77706b309223d19bf68ae5aa64b2cef`, followed by the local guidance/validation
work described below. This is a resume index, not a security audit or publication approval. Recheck
live state when resuming.

## Current state

- Patchground **0.1.0 is published** on [PyPI](https://pypi.org/project/patchground/) and as a
  [GitHub release](https://github.com/franndeli/patchground/releases/tag/v0.1.0).
- [patchground.dev](https://patchground.dev/) is live with seven built-in challenges. The repository
  registry contains no community packs.
- The optional guide skill and website prompt are shipped. This follow-up adds verified clipboard
  readback, static guidance checks, and three synthetic role trials. It does not publish those changes.
- Independent-human learner and author acceptance remains **pending recruitment**. Publication and
  synthetic completions do not establish that acceptance or waive future approval gates.

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
- Content: difficulty is not human-rated; there is only one beginner challenge. Use feedback to
  prioritize another beginner challenge or an independently authored community pack, not an arbitrary
  catalog target. No demand claim follows from model completions.
- Registry-name installation and a publish helper remain planned, not practice prerequisites.
- AI coaching/generation, stages, multi-container services, periodic history capture, and restoration
  remain deferred. No accounts, hosted execution, or overall scoring.
- Any future package release or production deployment needs separate explicit approval. The help
  wording fix and responsive layout fix are not yet evidence of changed published behavior.

## Verification context

The evaluation names exact artifacts and rerunnable commands. Local checks cover guidance, Python
lint/types/non-Docker tests, schema parity, site tests/build, real browser interactions, installed
candidate behavior, and the Docker-backed synthetic workflows. The full Docker integration suite
was not rerun for this follow-up; the role trials and coordinator author validation are narrower.

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
