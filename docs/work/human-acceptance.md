---
id: patchground-task-human-acceptance
type: task-spec
title: Establish independent learner and author acceptance
status: draft
parent: patchground-goal
references: [patchground-contract-cli, patchground-contract-security, patchground-contract-verification]
---

# Establish human acceptance

## Outcome

Determine whether someone unfamiliar with Patchground can complete a practice attempt and whether
an independent author can create a valid challenge from public guidance.

## Current evidence and owner decision

The package and site are public. `docs/evaluations/human-trial-findings.md` contains no human
session records. The ten-attempt cohort, fresh-wheel trials, and later guide/onboarding trials are
synthetic and cannot fill this gap. The latest results are in `docs/evaluations/agent-guide-smoke.md`.

During this project check, the owner selected “Keep trials pending”: publication is complete,
human acceptance remains unverified, and real learner/author trials are a priority. This does not
authorize inventing results, recruiting people without consent, or treating an agent as a human.

## Scope

Use the existing `docs/evaluations/human-trial-kit.md` and findings template; do not create another
competing protocol. The learner brief now uses the public installation path and built-in catalog,
not a source checkout. Recruitment remains pending because real participants were unavailable.

Recruit one unfamiliar learner and one independent author as required by the existing kit.
A maintainer arranges participants; an agent can prepare instructions, analyze consented redacted
notes, and implement approved follow-ups, but cannot satisfy the participant requirement.

Record the actual package version, public documentation revision, platform, challenge, time used,
and assistance. A participant's normal AI use is allowed. If the guide skill is used, record that
fact and its revision so assisted onboarding is not confused with unaided documentation use.

## Acceptance criteria

- The learner attempts install → discovery → start → check → submit → report from the published
  entry point, without source-repository or hidden-solution access.
- The author uses the public authoring guide to create a challenge, validate it in Docker, and
  solve it in a fresh session.
- Each finding is classified as blocker, friction, or positive with the participant's observed
  behavior and all facilitator interventions. Failure and unfinished attempts remain in the record.
- Existing kit pass criteria are applied explicitly: each session completes unassisted, or its
  assistance leads to a product/docs fix; no unresolved blocker remains.
- Fixes have linked commits and focused verification. Friction left unresolved has a reason and
  a next action. Follow-up attempts never replace the original observations.
- Records contain anonymous participant labels and consented summaries, not names, emails,
  screenshots of private work, credentials, home paths, or machine identifiers.
- The summary reports what these two sessions establish and what they do not: no general usability,
  demand, difficulty calibration, or market claims from a tiny sample.

## Dependencies and stopping conditions

Recruitment can start while documentation parity is addressed. Run the trials against identified,
coherent public instructions rather than knowingly contradictory guidance. If no humans are
available, mark this task blocked on recruitment; do not substitute more synthetic trials.

Do not reopen deferred AI coaching, generation, hosting, accounts, or overall scoring. A trial
finding that requires a behavior change gets its own accepted design and owning-spec update.

## Resume and verification

Read the trial kit, findings file, `docs/evaluations/agent-guide-smoke.md`, and current public
README. Ask the owner for participant availability. Execute the kit and review the redacted record
against every pass criterion. Automated tests validate resulting fixes, not the human gate itself.

## Completion

Update the findings and next-session index with the actual result and remaining blockers. Retire
this task-spec only when the agreed acceptance work is complete, not when participants are scheduled.
