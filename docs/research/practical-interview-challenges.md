# Practical SWE interview challenges for Patchground

Research date: 2026-11-04. Status: all eight challenges implemented in source. See the [implementation evidence](../evaluations/interview-batch.md) for validation and publication limits.

The owner approved eight original challenges across Python and TypeScript, with mixed difficulty, offline execution, and provisional difficulty estimates. This document explains the evidence and selection. The companion [implementation brief](../work/interview-challenge-implementation.md) records the approved implementation scope.

## What the evidence supports

Practical interview preparation should include reading an unfamiliar application, changing behavior against a written contract, testing failure paths, and explaining trade-offs. Employer-published material supports this format:

- Monzo describes a practical, non-LeetCode pairing exercise with a provided interface and automated tests. Its March 2025 article also describes a take-home alternative and a review of implementation decisions [S1].
- GitLab's live handbook describes reviewing a self-contained merge request and improving it during a 90-minute call. It explicitly distinguishes these curated exercises from work on real production issues [S2].
- Gigs publishes a webhook integration exercise involving duplicate messages, upstream errors, and rate limits [S3].
- Fly.io publishes a billing work sample with invoice models, monthly aggregation, and a deliberately unreliable mock payment provider [S4].

These sources support realistic work samples. They do not establish which questions most companies ask, how frequently a task appears, or whether a specific public exercise remains in use. No candidate survey or representative hiring dataset was collected.

### What “current” means here

The web was searched on the research date, including material dated 2025 and 2026. Current employer process pages are stronger evidence of interview format than old candidate repositories. A repository's creation date, recent indexing, or continued availability does not prove current hiring use.

Recent Stripe-specific task claims came from a commercial interview-report site [S8], not Stripe. They remain secondary reports even when the site supplies a “last asked” date. The proposed challenges are adaptations of skill areas, not replicas or promises about an upcoming interview.

## Source register

“Direct fetch” means the source page was retrieved and its extracted text inspected. “Search extract” means the search tool returned the page's content, but a separate fetch was not completed. The web-fetch service hit its hourly limit during follow-up checks. No upgrade or paid service was used.

### S1. Monzo: practical pairing and take-home review

- URL: https://monzo.com/blog/demystifying-the-backend-engineering-interview-process
- Publisher: Monzo. Published 1 March 2025. Direct fetch.
- Evidence: interface implementation with supplied tests, familiar languages and editor, practical day-to-day work rather than sorting or tree puzzles, discussion of choices.
- Limit: the article itself says it was accurate when published. It does not disclose the exact exercise.
- Use: overall challenge format and provisional 30–90 minute scope, not attribution of any selected topic to Monzo.

### S2. GitLab: review and improve a small application

- URL: https://handbook.gitlab.com/handbook/hiring/interviewing/technical/
- Publisher: GitLab. Live handbook, publication date not established. Direct fetch.
- Evidence: advance merge-request review, a 90-minute collaborative improvement session, curated self-contained exercises, and AI guidance.
- Limit: no specific bug or feature is disclosed. This is not evidence that GitLab asks any of the eight proposed tasks.
- Use: realistic tickets, established code, and debrief questions about review and communication.

### S3. Gigs: reliable webhook integration

- URL: https://github.com/gigs-hiring/backend-challenge/blob/main/CHALLENGE.md
- Publisher: Gigs hiring repository. Publication date and present hiring use not established. Direct fetch.
- Evidence: accept notification events, forward them to a webhook service, preserve idempotency, handle errors and rate limits, and discuss production readiness.
- Limit: the original requests Go or Ruby and a larger service. Our Python retry scheduler is a narrower original adaptation.
- Use: challenge 7. No external API, credentials, employer code, or original tests are needed.

### S4. Fly.io: billing models and aggregation

- URL: https://github.com/fly-hiring/backend-engineer-challenge
- Publisher: Fly.io hiring repository. Repository created in 2022 according to retrieved metadata. Direct fetch.
- Evidence: invoice and line-item modeling, monthly totals across years, mock provider integration, reliability and duplicate-billing concerns.
- Limit: historical public work sample, not confirmation of a 2026 hiring loop. The original is Rails-based.
- Use: challenge 4 focuses on aggregation rather than duplicating Patchground's existing payment-retry challenge.

### S5. Titan-Software: in-memory rate limiting

- URL: https://github.com/Titan-Software/backend-challenge-rate-limiter
- Publisher: a repository under Titan-Software presenting itself as a backend interview challenge. Created December 2025 according to search metadata. Direct fetch.
- Evidence: TypeScript rate-limiting middleware, per-client limits, expired windows, cleanup, no Redis dependency.
- Limit: the repository's description establishes its stated purpose, not independent confirmation of hiring use or employer identity. The original permits either fixed or sliding windows.
- Use: challenge 5 specifies one sliding-window contract so checks can be objective.

### S6. Swapcard: search application

- URL: https://github.com/Swapcard/frontend-challenge
- Publisher: Swapcard repository. Search metadata dates the repository to 2019. Search extract.
- Evidence: artist search, empty-search behavior, favorites, optional debouncing and infinite scrolling.
- Limit: historical public exercise. It does not explicitly request the stale-response bug used in our adaptation.
- Use: challenge 6 tests asynchronous search-state correctness. Stale-result handling is our engineering extension, not an employer-attributed question.

### S7. Rainforest: nested record editing

- URL: https://github.com/rainforestapp/rf-homework-frontend
- Publisher: Rainforest repository. Search metadata dates the repository to 2022. Search extract.
- Evidence: retrieve nested test-suite records, edit names and child records, validate fields, and serialize the result. Code quality matters more than visual design.
- Limit: historical public exercise. Our framework-free editing model omits the original UI and uses a different domain.
- Use: challenge 2 isolates data ownership, cancellation and validation without adding browser infrastructure.

### S8. Stripe practical-round reports

- URL: https://landthelab.com/companies/stripe/rounds/practical
- Publisher: Land the Lab, a third-party interview-report site. Search extract.
- Evidence: lists configuration-table merging as reportedly asked in April 2026 and an AI-assisted transaction-rule engine as reportedly asked in October 2026. Also lists debugging and integration tasks.
- Limit: unverified reports, some details paywalled. We did not access paid content, confirm reports with Stripe, or establish reporting methodology. Do not market these as “actual Stripe questions.”
- Use: challenges 1 and 8 take only the broad problem families. All requirements below are original Patchground design decisions.

### S9. Deliveroo cron-parser candidate repository

- URL: https://github.com/Sharjeel50/Deliveroo-Technical-Test
- Publisher: an individual candidate repository, not Deliveroo. Search metadata dates it to March 2024. Search extract.
- Evidence: self-described Deliveroo take-home cron parser.
- Limit: unverified historical candidate claim, not evidence of current use. The candidate's implementation was not inspected or copied.
- Use: challenge 3 applies the general parser problem to a scheduled-export configuration tool.

## Why these eight

The current seven examples cover cache expiry, CSV row errors, duplicate charges, event subscriptions, notification boundaries, pagination, and release-version ordering. Repeating those topics would increase count more than learning coverage.

The selected batch adds configuration precedence, immutable editing, syntax expansion, SQL aggregation, rate-window boundaries, asynchronous result ordering, retry scheduling, and safe rule evaluation. Four use Python and four TypeScript. Two are beginner, four intermediate, and two advanced. These are author estimates, not human-rated difficulty or measured completion times.

### 1. Configuration overrides discard valid values

`config-precedence` · Python · debug · beginner · 30 minutes. Evidence: S8, secondary.

A deployment preview merges settings from ordered configuration layers. The current code treats false, zero and empty strings as absent and resolves priority ties incorrectly. This is approachable production debugging rather than a parser puzzle.

The task exercises absent-versus-present values, stable precedence, and preserving caller input. It differs from CSV ingestion because it operates on already-parsed records with a fixed contract.

### 2. Cancelling an edit still changes saved records

`draft-edit-isolation` · TypeScript · debug · beginner · 30 minutes. Evidence: S7, historical primary exercise; the aliasing defect is our adaptation.

A team edits a shipment checklist. Changing a nested draft item unexpectedly changes the saved checklist before submission. Learners repair the editing model and retain its validation behavior.

The task exercises object ownership and state transitions. It does not require CSS, a browser, or React knowledge.

### 3. Expand a scheduled-export expression

`cron-field-expansion` · Python · feature · intermediate · 60 minutes. Evidence: S9, historical secondary.

An operations tool needs a human-readable preview of a five-field schedule. Learners complete a bounded parser for lists, ranges and steps, with useful errors. The tool previews fields; it never executes the command or schedules a job.

The task exercises parsing and boundary reasoning. Its grammar is deliberately smaller than a full cron implementation.

### 4. Monthly invoice totals are wrong

`invoice-monthly-summary` · Python · debug · intermediate · 45 minutes. Evidence: S4, historical primary exercise.

A billing dashboard merges January from different years and duplicates invoice totals through a line-item join. Learners repair an SQLite-backed report with organization isolation and integer-money arithmetic.

This adds database reasoning without introducing a database sidecar. It avoids the already-covered duplicate-charge mechanism.

### 5. Enforce a rolling request quota

`sliding-window-rate-limit` · TypeScript · feature · intermediate · 45 minutes. Evidence: S5, public interview repository with limited independent corroboration.

A small API adapter needs per-client rate limits. Learners implement a deterministic in-memory limiter with an injected clock. Exact boundary behavior is part of the ticket.

This is distinct from cache expiry: accepted requests consume capacity, rejected requests do not, and each client has its own rolling history.

### 6. Old search results replace the latest query

`search-response-ordering` · TypeScript · debug · intermediate · 45 minutes. Evidence: S6, historical primary exercise; race handling is our adaptation.

A catalog search model displays results for an earlier query after a newer response has already arrived. Learners fix request ownership across success, failure, clearing, and disposal.

The task uses controlled promises rather than real networking or timing benchmarks. It covers frontend engineering behavior without a visual redesign.

### 7. Retry webhook deliveries without blocking the queue

`webhook-retry-scheduling` · Python · feature · advanced · 75 minutes. Evidence: S3, primary public work sample with unconfirmed current use.

A notification worker needs bounded retry scheduling. It must honor rate-limit responses, distinguish transient and permanent failures, and make progress on unrelated deliveries.

The challenge focuses on retry state and readiness, not another duplicate-payment fix. Provider delivery remains an injected fake. Exactly-once delivery, crash durability and multi-worker locking are explicitly outside scope.

### 8. Evaluate transaction rules without executing code

`transaction-rule-evaluator` · TypeScript · feature · advanced · 75 minutes. Evidence: S8, secondary report.

A risk preview service receives a JSON rule tree and explains which rules match a transaction. Learners implement validation and evaluation with explicit types, bounded recursion and no dynamic code execution.

The problem exercises interpreter design and untrusted input. It uses a JSON tree rather than adding a textual expression parser, so it does not repeat challenge 3.

## Alternatives not selected

- Another paginated API sync or idempotent charge handler would overlap existing examples.
- A full React application adds browser setup and subjective UI evaluation. The two client-side behavior challenges isolate independently testable logic instead.
- Redis-backed limits, cloud queues and external billing accounts violate the intended offline, single-container scope.
- A full cron scheduler adds calendar and timezone policy beyond a compact interview task.
- Distributed scheduling and lease recovery deserve a separate advanced batch with accepted concurrency contracts.
- Algorithm puzzles remain useful elsewhere, but do not strengthen this product's real-codebase emphasis.

## Authorship and evaluation limits

All tickets, starter code, fixtures, checks and reference patches must be written originally. Public access is not a license to copy an employer's materials. Source links explain inspiration; they do not imply endorsement or license compatibility.

Model-authored challenges must declare generated provenance and the actual model identity when observable. Source confidence, challenge correctness and human usability are separate claims. Passing the validator proves the documented verification gates, not interview fidelity, educational quality or difficulty calibration.

No publication, release, production deployment or new paid service is approved by this research. Implementation is authorized locally. Independent-human acceptance remains open.
