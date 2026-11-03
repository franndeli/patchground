# Guide and onboarding synthetic trial protocol

## Purpose and limits

Exercise the corrected public guidance, published CLI, and standalone guide with three fresh agent
contexts. This is a bounded synthetic regression exercise, not a replacement for independent-human
acceptance, proof of demand, or a measurement of human completion time.

Source baseline: `01c399afe77706b309223d19bf68ae5aa64b2cef`, plus the documentation-parity edits
in this change. The coordinator freezes the supplied public files before launching workers and
records their SHA-256 hashes with the results. Workers use separately installed PyPI `patchground==0.1.0`
environments, separate session roots, and separate result directories. A source-built candidate wheel
is checked separately; it is not silently substituted for the published package.

Initial configuration: Pi `agent`, general-purpose, `opus` alias resolved to
`openai-codex/gpt-6.1-sol`, high reasoning. All three failed at startup because duplicate pstack
extensions registered conflicting tools; no trial actions ran. Replacement workers use the installed
Codex CLI, requested model `gpt-6-astra` with high reasoning, through visible managed Orca terminals
and existing subscription authentication. Record actual model metadata from the receipts/logs.
This is three role slices, not a model comparison. No paid credits or new service access.

Isolation is by separate writable directories and explicit source restrictions, not an adversarial
filesystem sandbox. Workers inherit repository/global safety instructions. Do not claim the guide
alone caused compliant behavior or that workers had no prior product knowledge in their system prompt.

## Slices and done predicates

### Learner

Public inputs: corrected README, first-session guide, standalone skill, and installed CLI help.
Pick the beginner built-in from the listing, use the printed workspace, add a regression test, solve,
check, submit, and read the report. Hints and visible diagnostics are allowed if recorded. Stop after
20 minutes or 40 CLI invocations. Never read package implementation, hidden checks, reference patches,
repository examples, or private session metadata. Record all blockers, help, and observed exit codes.

### Author

Public inputs: authoring guide and installed CLI help. Create a small Python debugging challenge
from the scaffold, adapting ticket, application, checks, and reference patch together. Mark generated
provenance honestly. Validate and then solve in a fresh session by editing its workspace, not by
applying the reference patch. Stop after 25 minutes or 40 CLI invocations. Authors may edit their own
source artifacts, but do not print hidden/reference contents or inspect other challenges' internals.
This author already knows the intended solution; the solve checks mechanics, not independent difficulty.

### Guide

Read only the standalone skill and supplied public docs, then answer seven fixed scenarios:
new-user setup; ambiguous session selection; test failure versus infrastructure error; next-step
navigation without solving; reset/submit/third-party consent; authoring; unavailable commands/docs.
Record exact replies and distinguish hypothetical advice from tool actions. Unsafe scenarios are
response-only: no destructive command, third-party execution, or real file upload. Use read-only help
and discovery to verify advice. Also try the public website prompt's skill URL. Stop after 15 minutes
or 30 CLI invocations. This single-worker sequence does not establish independent per-scenario trials.

## Evidence and adjudication

Each worker returns PASS, ISSUES, or BLOCKED with every observed issue, package version, source
baseline, method, commands, exit codes, and artifact locations relative to its own trial root. Keep
raw local output private; public summaries omit home paths, machine identifiers, credentials, hidden
sources, and reference patches. Do not invent hesitation, emotions, or human quotations for a persona.

The coordinator reads actual final session/report results, verifies test-backed outcomes and report
repeatability, and reviews action traces for source-boundary compliance. Agent self-reports alone are
not accepted as proof. Keep initial failures and any subsequent corrective reruns separate. If a
worker is unavailable, record the missing slice rather than count it as passed.

Repository checks validate skill metadata/links, reject deliberately broken guidance fixtures, and
exercise documented scaffold/discovery behavior. Browser checks separately verify visible-prompt
copy/readback, failure/manual fallback, and no-JavaScript availability. Passing these mechanical
checks does not establish conversational usefulness. Human trials remain explicitly pending.
