# Implement the practical interview challenge batch

Status: implemented in source; [validation and review evidence](../evaluations/interview-batch.md). Publication and human calibration remain separate gates. Research and source limitations: [research document](../research/practical-interview-challenges.md).

## Deliver the approved scope

Implement eight original challenges under `examples/`, four Python and four TypeScript. Use the IDs, types and estimated difficulty in the research document. Keep each challenge one stage with one ticket and one reference patch. Do not create a database or a new pack format.

The owner approved the proposed batch after selecting mixed difficulty, eight challenges and Python plus TypeScript. These acceptance criteria refine that approved scope. If implementation reveals a material product choice or a conflict with an owning spec, stop and ask rather than silently changing the task.

## Read the owning contracts

Read `AGENTS.md`, `docs/authoring.md`, `src/patchground/authoring/SPEC.md`, `src/patchground/spec/SPEC.md`, `web/SPEC.md`, and the challenge-format, execution, verification and security contracts under `docs/contracts/`. Inspect the existing packaging and catalog discovery paths before changing lists or counts.

Built-in catalog data comes from `examples/*/challenge.yaml`. `registry/index.json` and `registry/status.json` are CI-owned community outputs: do not hand-edit them. Existing discovery may already include new examples. Change packaging or CI enumeration only where inspection proves it necessary. Correct `examples/README.md`'s all-handmade description when generated examples are introduced. Do not change website layout or styling.

## Public acceptance criteria

Every behavior tested by hidden checks must appear in the public ticket. Hidden checks may vary inputs, not introduce secret requirements. Resolve exact exported names in the ticket and provide stable starter interfaces. Below are the required semantics, not mandatory internal designs.

### 1. config-precedence

Use a sequence of layers, each with an integer priority and an already-parsed mapping of string keys to JSON-compatible values. Higher priority wins per key. For equal priority, the later layer in input order wins. A missing key does not override; explicit null, false, zero, an empty string, an empty list and an empty object do override. Merge top-level keys only; nested values replace as a whole. Empty input produces an empty mapping. Do not mutate the input.

Provide one public entry point such as `merge_layers`. Treat layer shapes as prevalidated; do not expand into file parsing, environment-variable expansion or a schema system. Include both ordinary overrides and tie behavior in visible checks. Hidden coverage varies ordering, falsy values and nested replacement. The starter has a plausible precedence defect rather than an empty function.

### 2. draft-edit-isolation

Model a saved checklist with a name and items containing stable IDs, labels and a completed boolean. `begin_edit` returns an independent draft. Editing a nested item, adding an item or removing one must leave the saved record unchanged. Cancelling discards the draft. Saving a valid draft returns an independent saved value without mutating either argument. Subsequent draft edits must not alter the saved result.

Reject whitespace-only names or labels, an empty item list, and duplicate item IDs at save time with a documented structured error. A failed save leaves saved state unchanged. Preserve stable IDs and item order. No persistence, backend, DOM or visual UI is required. Visible checks explain success, validation and cancellation. Hidden checks vary aliasing paths and repeated editing sessions.

### 3. cron-field-expansion

Parse five whitespace-separated schedule fields followed by a nonempty command remainder. Expose expanded sorted unique integer values for minute 0–59, hour 0–23, day-of-month 1–31, month 1–12 and weekday 0–6. Support `*`, integer literals, inclusive ascending ranges, comma unions, and positive `/step` suffixes on `*` or ranges only. A step starts at the selected range's lower endpoint. Reject out-of-range values, reversed ranges, zero steps, empty union members, integer-with-step forms, extra slash syntax and missing fields or command. Name the offending field in errors.

The command is opaque data and is never executed. Strip separator whitespace before it and preserve the command remainder internally. No named months, macros, seconds field, timezone handling, actual date calculation or evaluation of day-of-week/day-of-month interaction. Visible checks document the supported grammar. Hidden checks combine only documented forms and invalid inputs. Avoid requiring a particular parsing algorithm.

### 4. invoice-monthly-summary

Use Python's built-in SQLite, with deterministic fixture setup inside the challenge container. Supply invoices with organization ID, invoice ID, UTC issue timestamp and status, plus integer-cent line items. Return ascending `YYYY-MM` totals for one organization within a half-open UTC interval `[start, end)`, including only issued invoices. Draft and void invoices are excluded. Sum each line item once. Negative credit lines are allowed. An issued invoice with no lines contributes zero and still creates its month bucket. Omit months with no qualifying invoices. Empty results return an empty sequence.

Years must remain distinct and neighboring organizations must remain isolated. Specify UTC ISO timestamps in one canonical format and use prevalidated inputs. No currencies, exchange rates or floating-point money. Include fixtures exposing join multiplication and year-boundary bugs. Keep database access in the existing supplied repository interface; do not impose an unmeasured performance threshold or a particular SQL query.

### 5. sliding-window-rate-limit

Implement a per-client in-memory limiter with positive integer capacity and window length in milliseconds. Inject a monotonic integer clock. At time `now`, only accepted requests with timestamps strictly greater than `now - window` consume capacity. Admit at most capacity requests in that interval. Rejected requests do not extend it. Clients are independent, including adversarial string keys such as `__proto__`. Calls at one timestamp are distinct requests.

Return an allowed flag and remaining capacity after the call. Provide an explicit cleanup operation that drops expired history, including idle clients, without affecting live limits. If cleanup observability is needed, define its public result in the starter rather than inspecting a private map in tests. No Redis, real timers, wall-clock sleeps or multi-process claims. Invalid constructor values fail with a documented error. Clock regression is outside scope because the injected clock contract is monotonic.

### 6. search-response-ordering

Use a framework-free TypeScript search model with an injected promise-returning transport. Starting a nonempty query clears previous results and errors, stores the trimmed query and enters loading state. Only the latest request may commit success or failure. Clearing with whitespace invalidates all in-flight work and returns an empty idle state without a transport call. Failure of the current request produces a documented error state with empty results. A stale failure must not overwrite a later success. Repeating the same query still starts a fresh request and invalidates the prior one.

Disposal invalidates in-flight requests and makes later search calls no-ops. Document how callers read state. Tests use explicitly controlled promises, including reverse completion order, not real latency or cancellation support. No debounce requirement or actual UI change. Give the starter a credible race defect in otherwise working code.

### 7. webhook-retry-scheduling

Provide a single-worker queue with unique delivery IDs, injected integer time and a deterministic fake sender. Each delivery starts pending with zero attempts and a due time. One drain call attempts each currently due delivery at most once, in `(due_at, delivery_id)` order, and continues after an individual delivery fails. Successful 2xx responses mark delivery complete. A timeout, 429 or 5xx schedules retry. Other statuses mark permanent failure.

Set maximum attempts to three total, including the initial attempt. After the first retryable failure schedule `now + 1000ms`, and after the second `now + 2000ms`. On 429, use the larger of that delay and a supplied nonnegative integer retry-after duration. Invalid or absent retry-after falls back to the normal delay. On the third failed attempt mark exhausted, with no future due time. Completed, permanently failed and exhausted deliveries are never sent again. A not-yet-due item remains unchanged. Retry scheduling uses the injected time of the drain call; no sleeping.

Accepting a repeated delivery ID is a no-op and must not reset terminal status or attempts. This is queue identity only, not an exactly-once delivery guarantee. No persistence across restarts, background threads, remote services or concurrent workers. Publish the state model and retry rules in the ticket. Hidden checks cover fairness, boundaries and exhaustion, never undisclosed infrastructure failure modes.

### 8. transaction-rule-evaluator

Accept named rules expressed as a JSON tree. Transactions have integer `amount_cents` and string `country` and `merchant`. Predicate nodes support numeric `gt`, `gte` and `eq` on amount, and string `eq` and `in` on the two string fields. Logical nodes support nonempty `all`, nonempty `any` and unary `not`. String comparison is exact and case-sensitive. Return every matching rule ID in input order; an empty rule list returns an empty result.

Validate the entire rule set before evaluation, including branches that short-circuit at runtime. Reject duplicate or empty rule IDs, unknown fields or operators, wrong value types, malformed node shapes and unknown node keys. Define a maximum depth of eight nodes along a root-to-leaf path, counting the root as one; depth nine is invalid. Errors identify the rule and tree path. Invalid transaction shapes return a documented validation error rather than silently coercing values. Inputs must not be mutated.

No `eval`, generated functions, regex language, text grammar, side effects, real fraud decisions or learning model. Validation and interpretation must be real implementation work, not delegated to a dependency that solves the challenge. Visible checks document every operator and error shape. Hidden checks vary combinations, depth, invalid short-circuited branches and input mutation.

## Author and verify each challenge

1. Use the matching existing starter's pinned environment and supported test conventions. Build-time downloads are allowed. Run-phase external networking is not.
2. Write original starter code, ticket, visible and hidden checks, hints, debrief and minimal reference patch. Never copy employer code or candidate solutions. Record `provenance: generated`, observable `generated_by.model`, and `prompt_version: interview-batch-v1`. Do not attribute the challenge to a human author who did not write it.
3. Keep hidden checks and solutions outside the workspace. Do not print hidden source, paste it into reports, or include it in site output. Make reference patches change application code, not weaken checks.
4. Run challenge commands only through `sandbox/` via `uv run pgnd validate examples/<id> --json`. Never run authored Python, pytest, npm test or Vitest on the host. Container runs must test both broken and reference states. `not_run` is not passing evidence.
5. Inspect every validation gate, including determinism and tampering checks. Record pass/fail per challenge and explain any blocker. Do not label a challenge verified when Docker is unavailable.
6. Exercise real session `start` and `check` behavior in disposable sessions without changing an existing learner workspace's Git state. Confirm visible entry points are usable and protected material is absent from the learner workspace.
7. Run repository lint, types, affected tests, package/catalog checks and the website build as applicable. Repository tests are distinct from challenge code and may run on the host. Ensure packaged resources and the generated catalog include all eight. Do not hard-code a count unless an existing contract requires one.
8. Review the diff, apply deslop before commits, and follow the repository's independent review gate before a nontrivial PR. Update owning specs only where the change alters their contract or documented invariant. Do not claim CI green without observing CI.

At handoff, summarize files, the actual model, each challenge's validation result, catalog/package verification, and what remains unverified. Human difficulty calibration remains open even if all checks pass.

## Explicit exclusions

No core runner redesign, new database, hosted execution, new language, stages, overall scoring, AI coaching, registry edits, live service credentials, paid upgrades, deployments, package publication or releases. Do not change security guards or weaken failing validation to finish. Do not publish research claims as employer endorsements. Leave unrelated user changes intact.
