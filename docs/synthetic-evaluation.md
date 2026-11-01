# Synthetic learner evaluation protocol

## Approved scope

Ten independent attempts across available model capability tiers, not ten necessarily distinct
model IDs. Use existing authenticated subscriptions and local models only. At most two learners
run concurrently. Each attempt stops at its challenge's declared timebox or 20 `check` invocations,
whichever comes first. No extra paid inference is authorized.

This is a product-diagnostic cohort, not ten human learners, a statistical model leaderboard or
proof of usability/demand. A capable model completing an exercise does not establish that a human
understood the ticket. Human onboarding and independent-human authoring gates remain separate.

## Before the cohort

1. Freeze the product commit, challenge revisions and public instructions; validate each challenge.
2. Smoke-test selected model/agent configurations through the same visible supervised runner. A CLI
   being installed or authenticated is not proof a specific model or tool-use mode works.
3. Register the ten assignments before collecting outcomes. The owner approved coverage of all six
   curated Python/TypeScript challenges: each receives at least one attempt, with the remaining four
   used for cross-model comparisons. Spread attempts across available tiers; explain unavoidable
   imbalances and unavailable models.
4. Record exact model ID and agent version/configuration where available. Do not infer capability
   rankings from marketing names; tier labels are hypotheses, not measured results.
5. Verify original/reference artifacts stay outside learner-provided material. Provide only the
   public instructions, ticket and editable workspace/visible checks. Do not copy implementation
   team discussions, reference patches, hidden sources or earlier learners' answers into prompts.

## Execution

- Use a fresh workspace and session per attempt, with no shared writable working tree.
- Give identical task instructions and access rules for a given challenge. Learners may use the
  shipped CLI and their own edits; challenge execution remains container-only.
- Use a supervised Orca Task/Dispatch per attempt. Record actual launch and settlement evidence;
  a queued prompt is not a completed attempt. Keep runtime handles/local paths in private resume
  notes, not committed public reports.
- Observe the timebox and check budget. Record stop reason and any coordinator intervention.
  Do not silently provide a fix, reset the clock, increase the budget or relabel assisted success
  as unassisted success. Separate tool/environment recovery from coaching assistance.
- Prompt restrictions and separate folders are not a security sandbox against a malicious agent.
  Document the real access boundary and any contamination; contaminated attempts are not blinded
  evidence. Do not claim that hidden checks are inaccessible on a local machine.
- Do not run learner workers in the implementation checkout. No credentials are copied into their
  files or logs. Existing provider authentication remains managed by its configured client.

## Per-attempt record

Record sanitized structured facts, with unknown values explicit:

- attempt ID, product commit, challenge ID/revision and task assignment;
- requested and observed model/agent configuration, capability-tier hypothesis;
- timebox, elapsed time, check count, hint count and stop reason;
- commands attempted and their structured outcomes, not hidden sources or raw private traces;
- assistance and environmental recovery provided, including whether instructions changed;
- final test outcomes and regression-test outcome when the product can establish it;
- workflow blockers, unexpected messages and minimal reproducible product defects;
- reference exposure or other contamination, if any;
- outcome category and evidence supporting it.

Outcome categories: completed unassisted, completed assisted, solver failure, product defect,
environment failure, budget exhausted, contaminated or inconclusive. Categories can include
secondary findings; do not turn them into an overall engineering score.

## Remediation and reporting

Keep original attempts immutable in the evaluation record. A retry after a product fix is a new
attempt linked to the original, with its own commit and configuration. Repeat affected acceptance
checks and record whether the reproduced product defect is fixed.

Publish a sanitized aggregate report: coverage, observed completion counts, blockers, fixes,
remaining limitations and recommendations. Do not publish provider tokens, personal paths,
machine identifiers, raw credential-bearing transcripts or hidden/reference sources. Optional
provider usage statistics are observations only, not inferred bills.

## Current status

The owner approved all-six-challenge coverage and a four-Codex/four-Sonnet/two-Haiku mix.
All three configurations passed visible supervised file-read/write smoke tests; the exact
configuration evidence and ten assignments are registered in
[`evaluations/learner-cohort-registration.json`](evaluations/learner-cohort-registration.json).
The frozen core-only wheel and all six challenges passed installed-CLI Docker validation.
Shared instructions are in [`evaluations/learner-instructions.md`](evaluations/learner-instructions.md).
No learner attempt has run at registration. The separately owned website is outside this CLI
candidate evaluation, and independent-human acceptance remains pending.
