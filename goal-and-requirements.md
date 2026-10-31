---
id: patchground-goal
type: goal-and-requirements
status: draft
title: Patchground — Goal and Requirements
---

# Patchground

*Real code. Real problems. Your tools.*

## Overview

Patchground is an open-source, local-first engine for practicing real software engineering. A CLI
(`patchground`, alias `pgnd`) drops the user into a broken or incomplete repository, lets them solve
it in their own editor with whatever AI they use (or none), verifies the work in a container, and
reports what it could verify — then, optionally, debriefs them like an interviewer would.

It is an engineering practice engine that happens to work with AI, not an AI-powered interview
platform: the project pays for no inference, hosts no models and ships no coding assistant.

It has two layers that stay separate, like Docker and Docker Hub:

- **The format and the runner** — how a challenge is packaged, run and verified. This is the product.
- **The packs** — git repositories of challenges that make them shareable. This is where the
  community lives.

## Problem Statement

Technical interviews are moving from algorithm puzzles to realistic work: debugging unfamiliar code,
adding features to existing repos, reviewing PRs, and using AI tools under scrutiny. There is no
standard, free way to practice these formats:

- **No structured path.** For live-debug or pair-programming rounds the advice is "fix a random
  open-source issue": unstructured, ungraded, no feedback.
- **Paywalls on API wrappers.** Realistic-practice products charge subscriptions largely to cover AI
  and hosted sandboxes the user could run themselves.
- **Output, not judgment.** Practice platforms grade output; employers increasingly look at process —
  navigation, hypotheses, testing, and catching an AI tool's mistakes.

## Target Users

In priority order:

1. Engineers preparing for practical or AI-assisted interview rounds (the core user; the author is one).
2. Junior developers learning to work in codebases they did not write.
3. Experienced engineers sharpening a specific skill (concurrency, debugging, review, a new stack).
4. People learning to direct and validate coding agents.
5. Challenge authors — anyone writing a challenge against the open format without knowing the engine.

The product is framed as engineering practice; interview prep is the entry point, and the format must
not be limited to it.

## Jobs to Be Done

- When I have a practical interview coming, I want a realistic broken repo to fix under a timebox in
  my own setup, so I can rehearse the round instead of grinding puzzles.
- When I finish an attempt, I want to know what is verifiably true about my work (checks, whether my
  test really catches the bug, scope of my diff), so I can tell skill from luck.
- When I know a good bug from my own work, I want to package it as a challenge and prove it is sound,
  so others can practice on it.

## Key User Story

Ana has a live-debugging round next week. She runs `pgnd start duplicate-charges-on-retry`, opens the
printed workspace in her editor with Claude Code, reads the ticket, and reproduces the double charge.
`pgnd check` shows two hidden checks red. She writes a regression test, fixes the retry path, and
checks again: 14/14. `pgnd submit` reports 38 of 45 minutes, a regression test verified to fail before
and pass after, and a diff confined to `src/payments/`. No account, no API key, no network after the
image build.

## Goals

- A new user installs with one command and completes a challenge in their own editor without help.
- Every predefined challenge is fully playable offline, with no API key, after its image is built.
- Someone other than the author can write a challenge from the docs alone and pass `pgnd validate`.
- Every published challenge is proven in its container: the broken state fails and a reference
  solution passes, deterministically. Reusable in-repository CI automation applies that same verifier
  to committed changes with explicit execution consent, factual JSON and no checkout mutation.

## Principles

Hard constraints; when a feature conflicts with one, the principle wins.

1. **Local-first.** Everything core runs on the user's machine. No account, server or subscription.
2. **AI optional, never required.** AI features are opt-in and BYOK; the core works without them.
3. **Bring your own tools.** The user works in their real editor and real agent.
4. **Verified or it doesn't ship.** A challenge must show in its container that its broken state fails
   and a reference passes. That shows consistency, not completeness or realism; an LLM's opinion is no
   evidence.
5. **Outcomes first, then coaching.** Verified facts and coaching are never mixed; "not observed" beats
   guessing; no overall score.
6. **Format before platform.** The challenge format is the product; the CLI is its reference
   implementation.
7. **Quality over quantity.** Five excellent challenges beat fifty generated ones.
8. **Honest about safety.** Challenge commands never intentionally run on the host; untrusted packs
   need explicit consent before anything is built or run.
9. **Privacy by default.** Nothing leaves the machine unless the user runs an AI feature, and then only
   the minimum context, shown beforehand.

## Glossary

Code, docs and CLI output use exactly these terms.

| Term | Meaning |
| --- | --- |
| Challenge | One self-contained exercise in one folder: starting codebase, ticket, checks, reference solution, optional debrief questions. |
| Challenge type | `debug`, `feature`, `review`, `refactor` (format v0.1); `incident`, `ai-validation`, `design` are reserved. |
| Pack | A versioned collection of challenges, distributed as a git repository with a `pack.yaml` index. |
| Session | One attempt at a challenge by one user: its workspace, timer, event log and report. |
| Workspace | The git repo the user edits, created fresh per session outside the pack. |
| Check | Running a challenge's verification against the workspace, inside a container. |
| Debrief | The end-of-session report: verified outcomes first, then optional AI coaching. |
| Stage | Reserved; progressive requirements inside one challenge. Not in the format until a model exists that builds on any valid earlier solution. |

## Capabilities

- **Public documentation and challenge catalog** at `patchground.dev`, supporting discovery,
  installation and authoring without accounts or hosted execution. The CLI remains the runner.
- **Open challenge format** with a published JSON Schema and precise, file-and-line errors
  (`patchground-contract-challenge-format`).
- **Play a challenge:** list and show challenges, start a session (build image, create workspace,
  print ticket), check, reset, status, progressive hints, and running commands in the challenge
  container (`patchground-contract-cli`). Browse local attempts and read optional privacy-filtered
  initial/check checkpoint history without changing learner Git state; diagnostic container edits
  are discarded.
- **Isolated verification:** every check runs in a container on an internal-only network with
  resource limits (`patchground-contract-execution`).
- **Challenge validation and scaffolding:** `pgnd new` and `pgnd validate`, CI-friendly
  (`patchground-contract-verification`).
- **Verified-outcomes report** on submit, including whether the user's regression test fails before
  and passes after (`patchground-contract-feedback`).
- **Environment doctor** that checks Docker, git and disk and prints exact fixes.
- **Git-distributed packs** from public HTTPS or committed local repositories, pinned by commit
  and content identity, with explicit execution consent, reviewed updates and unambiguous discovery.
  Removing a pack never removes existing sessions (`patchground-contract-security`).
- **Optional AI layer (BYOK):** an interviewer-style debrief and challenge generation from a supported
  repo, both experimental and kept only if they prove useful (see `patchground-architecture`).

## Non-Goals

- Hosting sandboxes, accounts or inference; shipping an IDE or coding assistant.
- Proctoring or anti-cheating: hidden tests live on the user's machine; it is an honor system.
- An overall score or weighted grade.
- Watching keystrokes or the screen.
- Native Windows: Windows is supported through WSL2 + Docker Desktop only.
- Telemetry by default.

## Non-Functional Requirements

- Core installs and runs without the `[ai]` extra and without network after the image build.
- Default check limits: 2 CPUs, 2 GB memory, 512 PIDs, 10 minutes wall clock.
- Every command supports `--json`.

## Technology

| Aspect | Choice | Rationale |
| --- | --- | --- |
| Language / packaging | Python 3.12+, `uv`; install via `uv tool` or `pipx` | One-command install for developers |
| CLI | Typer + Rich | Typed commands, good help and terminal reports |
| Schemas | Pydantic v2 | Validation errors, JSON Schema export, structured LLM output |
| Containers | Docker SDK for Python (Podman via its Docker-compatible socket) | Isolation without writing a sandbox |
| Git | `git` subprocess behind a thin wrapper | Fewer surprises than a library; git is required anyway |
| Test results | JUnit XML via `junitparser` | One results contract for every language |
| AI | `anthropic`, `openai` SDKs as the optional `patchground[ai]` extra | Core installs without AI deps |
| Quality | pytest (`@pytest.mark.docker` for integration), ruff, mypy strict on `spec`, `verify`, `report` | |
| Docs | MkDocs Material, the format as centerpiece | |
| License | Apache-2.0 for the CLI; each challenge declares `content_license` (default CC-BY-4.0) | Low adoption friction |

## Alternatives Considered

Patchground's edge is the combination none of these offer: open source, local, BYO AI, an open
challenge format, and challenges verified in their container. Vendor details accessed Oct 2026.

| Alternative | What it is | Gap |
| --- | --- | --- |
| [CodeSignal](https://codesignal.com), [CoderPad](https://coderpad.io), [Byteboard](https://byteboard.dev), [HackerRank Code Repository questions](https://support.hackerrank.com/articles/1900882930-code-repository-questions) | Employer-side repo and AI-assisted assessments | Paid, hiring-side only |
| [nrml](https://nrml.dev), [Nyrion](https://nyrion.ai) | Hosted freemium practice for AI-assisted rounds on small repos | Hosted, closed content, platform-provided AI |
| [Gronex](https://gronex.org) | Hosted backend practice: fix a repo's failing tests, incidents, AI follow-ups | Hosted, freemium, closed content |
| [DiffDojo](https://diffdojo.com) | Hosted PR-review practice against a canonical review | Review only, hosted, closed content |
| [AI Coding Interview Practice](https://github.com/azizu06/ai-coding-interview-practice) | 10 local Python exercises solved with your own agent | Closest concept; fixed synthetic set, no container verification, no format |
| [Recticode](https://github.com/Recticode/python-cli) | CLI that pulls a mini codebase with a bug or feature task | Closest CLI shape; licence, activity and openness of the format unconfirmed |
| [GrillKit](https://github.com/GrillKit/grillkit), [Intervu](https://github.com/vvknyn/interview-os), [InterviewLab](https://github.com/javedshaik1228/interviewlab), [Interviewa](https://github.com/sh78ba/Interviewa) | Self-hosted BYOK mock interviewers | Q&A or chat; no real repos |
| [Exercism](https://exercism.org) | Nonprofit practice with an OSS CLI and community tracks | Small exercises, not real codebases |
| [The Last Deploy](https://github.com/thelastdeploy/thelastdeploy), [cka-lab-runner](https://github.com/CuriousLearner/cka-lab-runner) | Local break-then-fix labs | Infrastructure, not application code |
