# Project health and next sessions

Baseline: `565f350`, which committed and pushed the guidance/validation follow-up. The practical
interview batch described below adds local source content after that baseline. This is a resume
index, not a security audit or publication approval. Recheck live state when resuming.

## Current state

- Patchground **0.1.0 is published** on [PyPI](https://pypi.org/project/patchground/) and as a
  [GitHub release](https://github.com/franndeli/patchground/releases/tag/v0.1.0).
- The last observed [published catalog](https://patchground.dev/catalog.json) has seven built-in
  challenges. Source now contains fifteen, including the eight approved practical interview
  challenges. The repository registry contains no community packs.
- The optional guide skill and website prompt are shipped. Commit `565f350` added verified clipboard
  readback, static guidance checks, and three synthetic role trials. A source push alone does not
  establish a website deployment or a new PyPI release.
- The interview batch is implemented under `examples/`, not just described in research. Its local
  wheel and generated site include all eight IDs. See [batch evidence](evaluations/interview-batch.md)
  for validation, review corrections, artifact identity, and remaining limits.
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
- Content: the source catalog now includes three beginner challenges. Difficulty and timeboxes
  remain author estimates. Calibrate the expanded catalog with human feedback before claiming
  interview fidelity, usefulness, or measured completion times.
- Registry-name installation and a publish helper remain planned, not practice prerequisites.
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
