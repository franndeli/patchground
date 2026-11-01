# Ten synthetic learner attempts

## Result

All ten registered attempts submitted passing checks within their timeboxes, without coordinator
help or recovery during an attempt. Nine submissions established before-fail/after-pass regression
evidence; one correctly reported `not_established`. These are workflow outcomes, **not engineering
scores, a model ranking or independent-human acceptance**.

The [registration](learner-cohort-registration.json) was published in commit `ba0a740` before any
learner attempt. The frozen CLI/challenge revision was `44da6dd238bff5ce7c367f542dcba539dec29299`.
A core-only wheel installed in a fresh Python 3.12 environment validated all six challenges through
the installed CLI and Docker before the cohort. The separately owned website was not part of this
candidate evaluation.

[Structured per-attempt facts](learner-cohort-results.json) retain check outcomes, elapsed times,
regression states, structural test observations, changed-file counts and evidence limits. The shared
[learner instructions](learner-instructions.md) were identical apart from assignment, executable,
workspace, timebox and public ticket.

## Coverage and observed outcomes

The approved mix was four configured-Codex, four Sonnet and two Haiku attempts, at most two
concurrently, across four Python and two TypeScript challenges. Seven attempts used Python and three
TypeScript. Four challenges received cross-configuration repetitions; two received one attempt each.

- **L01:** Codex, payment retries — 26 passing checks; regression verified; two practice checks.
- **L02:** Sonnet, cache expiry — 25 passing checks; regression verified; one practice check.
- **L03:** Haiku, pagination — 11 passing checks; regression verified; one practice check.
- **L04:** Codex, CSV row errors — 150 passing checks; regression verified; two practice checks.
- **L05:** Sonnet, payment retries — 25 passing checks; regression verified; one practice check.
- **L06:** Codex, EventBus — 50 passing runtime checks; regression verified; two practice checks.
- **L07:** Sonnet, CSV row errors — 174 passing checks; regression verified; two practice checks.
- **L08:** Haiku, cache expiry — 35 passing checks; regression verified; one practice check.
- **L09:** Codex, release ordering — 16 passing runtime checks; regression verified; two practice checks.
- **L10:** Sonnet, EventBus — 48 passing runtime checks; regression not established; two practice checks.

There were 16 recorded practice-check invocations, no hints and no budget exhaustion. Saved session
timers ranged from approximately 19.4 to 66.9 seconds. Those timings include the prepared-session
handoff, not independent installation, and are not comparable performance benchmarks. Different
learners added different tests; larger passing counts do not establish stronger tests or engineering.

## Findings checked against artifacts

### Conservative TypeScript evidence remained honest

L10 used `expect.assertions(2)`, outside the bounded static adapter's recognized assertion calls.
Runtime checks passed, but both regression and structural-test evidence remained `not_established`.
An inert parse of a scratch copy without that counter recognized nine test definitions, identifying
the limitation without executing TypeScript on the host. No learner file or immutable report was
changed, and the attempt was not rerun or upgraded to verified regression evidence.

Empty removal/reduction lists in an unsupported result are not proof that nothing was removed or
reduced. L10's unknown structural counts are therefore represented as null in the aggregate record.
Supporting further Vitest forms would require a separately reviewed evidence-boundary change.

### Learner narratives were not accepted as ground truth

L08 reported that its committed starting files contained only ellipsis bodies. The coordinator
compared the three named initial Git blobs against the frozen challenge: every byte matched, and
none contained an ellipsis-only line. The original files had implementations. The cause of the
learner/tool-view mismatch is unestablished; this is not evidence that Patchground supplied stubs.

Initial tracked files for all ten attempts were independently matched against the committed workspace
and visible-check layers. Reports and actual diffs, rather than worker descriptions, supply the
published facts. In particular, L07's claimed change to `models.py` was absent from the saved diff.

### Passing checks did not erase structural observations

L05 and L08 each had two structural assertion-count reductions in existing tests. Both still passed
runtime checks and established regression evidence. These counts describe source structure, not a
semantic judgment that the revised tests are weaker or stronger; no overall score was introduced.

No confirmed Patchground product defect requiring a code fix was reproduced in this cohort. The
unreproduced Docker OOM-classification symptom tracked separately is not declared fixed by these runs.

## Safety and provenance checks

- Every learner had a fresh workspace outside the implementation checkout. Only the public ticket,
  instructions, editable source and visible checks were provided; no earlier solution or worker
  conversation was copied into a later prompt.
- The coordinator installed the candidate and started each session. That setup is disclosed; the
  `completed unassisted` category means no help or recovery **during the solving attempt**, not a
  full independent onboarding trial.
- All ten final learner Git byte inventories matched their pre-handoff inventories. Reading each
  saved report twice returned identical JSON and preserved immutable submission bytes.
- Native Orca Tasks/Dispatches recorded completion. All ten learner workers and three configuration
  smoke workers were settled and released; unrelated user-owned terminals were left alone.
- Bounded tool-call inspection found no indicated hidden/reference read or authored host execution.
  Flagged Python invocations were empty interpreter probes or text-edit helpers, not application/test
  execution. Transcript content was clipped: this is not an exhaustive trace audit. Separate folders
  and prompt restrictions are not a security sandbox against a malicious local agent.
- Model details are in the registration. Codex's configured model was `gpt-6.1-sol`, but its effective
  backend identity was unavailable. Claude model IDs were worker-reported runtime metadata, not
  independent provider attestation. No model ranking is inferred from these labels.
- Existing ChatGPT/Claude Max access was used; no inference purchases or model downloads occurred.
  The local Ollama learner configuration was not included or evaluated in this cohort.

## Remaining acceptance

Independent-human onboarding and authoring remain pending. This cohort did not exercise independent
installation/discovery, human understanding, market demand, website usability or every error/hint/
diagnostic/history flow. Existing automated coverage is separate evidence, not a substitute.

AI coaching and challenge generation are explicitly deferred from launch. The website remains with
its separate owner. DNS, production deployment, package publication and release creation still require
explicit approval. The appropriate next step is human acceptance and coordinated release-artifact
review, not a claim that ten synthetic completions satisfy those gates.
