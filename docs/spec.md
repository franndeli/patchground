# Patchground — Project Spec

> **Background and roadmap only.** The authoritative record of the product, architecture and contracts
> is the spec graph: `goal-and-requirements.md`, `architecture.md`, `docs/contracts/*.md` and
> `src/patchground/*/SPEC.md`. Where this document and a spec disagree, the spec wins.

Oct 29, 2026 · @Francisco José Delicado González

## 1. Vision

Patchground is an open-source, local-first engine for practicing real software engineering: real codebases, real problems, your own tools.

**Tagline:** *Real code. Real problems. Your tools.*

**One-liner:** a CLI that drops you into a broken or incomplete repository, lets you solve it in your own editor with whatever AI you use (or none), verifies your work in a container, and then debriefs you like an interviewer would.

**Positioning.** Patchground is not an AI-powered interview platform. It is an engineering practice engine that happens to work with AI. The project pays for no inference, hosts no models and ships no coding assistant. Users bring Claude Code, Codex, Cursor, Copilot, a local model, or nothing.

**The Docker / Docker Hub analogy.** Patchground has two layers that must stay separate:

- **The format and the runner** define how a challenge is packaged, run and verified. This is the core product.
- **The packs and (later) the registry** make challenges discoverable and shareable. This is where the community lives.

If the format is good, people contribute challenges the way they contribute to Exercism tracks. The library is not a moat by itself, since incumbents can add similar features. What can set Patchground apart is a trusted set of genuinely excellent exercises, easy local runs, low-friction authoring and a recognizable community.

## 2. Problem and users

Technical interviews are moving from algorithm puzzles to realistic work: debugging unfamiliar code, adding features to existing repos, reviewing PRs, and using AI tools under scrutiny. LeetCode is not dead, but it no longer covers what these rounds test, and there is no standard, free way to practice the new formats.

**The pain points:**

- **No structured practice path.** LeetCode gives a clear grind. For live-debug or pair-programming rounds, the usual advice is "pick a random open-source issue and fix it": unstructured, ungraded, no feedback.
- **Paywalls on API wrappers.** Most realistic-practice products charge a subscription, largely to cover AI and hosted sandboxes the user could run themselves.
- **Practice platforms test output, not judgment.** What employers increasingly want to see is process: how you navigate, form hypotheses, test, and whether you catch an AI tool's mistakes.

**Target users, in priority order:**

1. Engineers preparing for practical or AI-assisted interview rounds (first and core user; Fran is one).
2. Junior developers learning to work in codebases they did not write.
3. Experienced engineers sharpening a specific skill (concurrency, debugging, code review, a new stack).
4. People learning to direct and validate coding agents effectively.

**Framing rule:** the product is framed as engineering practice, not only interview prep. Interview prep is the entry point and the marketing hook; the format must not be limited to it.

## 3. Landscape and differentiation

"LeetCode, but with real repos, debugging and AI" is already being built by several companies. Patchground wins only on the combination nobody offers: open-source, local-first, BYO AI, an open challenge format, and verified community and generated challenges.

| Player | Side | What it does | Gap Patchground fills |
| --- | --- | --- | --- |
| [CodeSignal](https://www.owler.com/reports/owler/Press-Release--CodeSignal---CodeSignal-Launches-Industry-First-Agentic-Coding-Assessments-for-AI-Era-Engineering-Hiring/1775178133271) | Companies | Agentic coding assessments with Claude Code, Cursor, Codex (Apr 2026) | Paid, hiring-side only |
| [CoderPad](https://www.interviewquery.com/p/coderpad-tech-interview-2026-format) | Companies | 60-minute real-codebase sessions with AI assistants | Paid, hiring-side only |
| [Byteboard](https://parse.gl/brands/byteboard-dev) | Companies | Real-world, project-style assessments | Paid, hiring-side only |
| HackerRank | Companies | Reportedly moving to repo tasks and AI fluency (Oct 2026) | Paid, hiring-side only |
| nrml, Nyrion, DiffDojo, Gronex | Candidates | Hosted practice: real repos, AI-assisted rounds, PR review, backend incidents | Hosted, mostly paid, closed content |
| [Intervu](https://github.com/vvknyn/interview-os), [InterviewLab](https://github.com/javedshaik1228/interviewlab), [Interviewa](https://github.com/sh78ba/Interviewa), GrillKit | Candidates, OSS | Self-hosted BYOK mock interviewers | Q&A, LeetCode or system-design chat; no real repos |
| AI Coding Interview Practice (OSS repo) | Candidates, OSS | \~10 repo exercises solved in your own editor and agent | Closest concept; small fixed set, no format, generator or debrief |
| Exercism | Learners, OSS | Open-source practice with a CLI and community tracks | Small exercises, not real codebases |

Note: rows without links came from a parallel ChatGPT research pass and have not been re-verified. Check them before relying on any claim about them.

**Differentiators, in order of importance:**

1. **Challenge quality and verification.** Every challenge, handmade or generated, is checked in its container: the bug is observable and a reference solution passes. Official packs add human review. Quality decides everything.
2. **An open, documented challenge format** anyone can author against without understanding the engine.
3. **Process-based debrief,** grounded in verified outcomes (including whether your regression test really catches the bug), plus optional AI coaching that questions your decisions.
4. **Generate challenges from supported repos** with your own AI, verified before you see them.
5. **AI validation scenarios:** challenges where the trap is a plausible but wrong AI-generated fix (planned for a later format version).

## 4. Product principles

These are hard constraints for every design decision. When a feature conflicts with one, the principle wins.

1. **Local-first.** Everything core runs on the user's machine. No account, no server, no subscription required.
2. **AI optional, never required.** Every predefined challenge works fully offline with no API key. AI features (debrief, generation, hints) are opt-in and BYOK.
3. **Bring your own tools.** Patchground never ships an IDE or a coding assistant. The user works in their real editor and real agent, exactly as in modern interviews.
4. **Verified or it doesn't ship.** A challenge must show, inside its container, that its broken state fails and a reference solution passes before it is published. That shows the exercise is consistent, not that it is complete or realistic. An LLM saying it is correct is no evidence at all.
5. **Outcomes first, then coaching.** Reports separate verified facts (checks, regression test) from coaching feedback, and say "not observed" instead of guessing. No overall score.
6. **Format before platform.** The challenge spec is the product. The CLI is its reference implementation; a website comes much later.
7. **Quality over quantity.** Five excellent challenges beat fifty generated ones. Curated packs come before generation and community.
8. **Honest about safety.** Patchground never intentionally runs challenge commands on the host. Official packs are reviewed; third-party packs are untrusted and need explicit consent before their environments are built or run.
9. **Privacy by default.** Nothing leaves the machine unless the user explicitly runs an AI feature, and then only the minimum context, shown beforehand.

## 5. Core concepts

Eight nouns define the whole system; code, docs and CLI output must use exactly these terms.

| Term | Definition |
| --- | --- |
| Challenge | One self-contained exercise: a starting codebase, a ticket, verification, reference solution, optional debrief questions. Lives in one folder. |
| Challenge type | `debug`, `feature`, `review`, `refactor`, `incident`, `ai-validation`. `design` (system design) is reserved for later. |
| Stage | Not in format v0.1. Reserved for progressive requirements inside one challenge, once there is a model that works on top of any valid earlier solution, not just the reference. |
| Pack | A versioned collection of challenges, distributed as a git repository with a `pack.yaml` index. |
| Session | One attempt at a challenge by one user: its own workspace, timer, event log and final report. |
| Workspace | The git repo the user actually edits, created fresh per session outside the pack. |
| Check | Running a challenge's verification (visible and hidden tests, invariants) against the workspace, inside a container. |
| Debrief | The end-of-session report: verified outcomes first, then optional coaching from an AI interviewer. |

**The core loop:**

1. `start` creates a session and a workspace from a challenge.
2. The user reads the ticket and works in their own editor and tools.
3. `check` runs verification as often as they like; each run is logged, and nothing touches the user's branch or staging area.
4. `submit` ends the session; `debrief` shows verified outcomes and, optionally, AI coaching.

## 6. Challenge format (v0.1)

Format v0.1 is deliberately small: one stage, one ticket, one reference solution, one test command. The schema accepts `x-` prefixed extension keys so experiments don't break it, and rejects any other unknown key.

### Directory layout

```
duplicate-charges-on-retry/
├── challenge.yaml        # manifest (required)
├── TICKET.md             # the task as the user sees it (required)
├── workspace/            # starting codebase, copied into each session (required)
├── environment/
│   └── Dockerfile        # runtime image; dependencies installed here
├── checks/
│   ├── visible/          # tests copied into the workspace
│   └── hidden/           # tests run only by `check`, never copied
├── artifacts/            # optional: logs, screenshots, data shown to the user
├── solution/
│   └── reference.patch   # never copied into the workspace
└── debrief/
    └── questions.md      # optional interviewer prompts
```

### challenge.yaml example

```
spec_version: "0.1"
id: duplicate-charges-on-retry
version: 1.0.0
title: Duplicate charges after a payment retry
type: debug               # v0.1: debug | feature | review | refactor
summary: A retry path charges customers twice. Find the root cause and fix it with a test.
languages: [python]
tags: [idempotency, retries]
difficulty: intermediate  # beginner | intermediate | advanced
timebox_minutes: 45
ai_policy: allowed        # allowed | forbidden
environment:
  dockerfile: environment/Dockerfile
  services: []            # optional sidecars, e.g. ["postgres:16"]
  test_command: pytest -q --junitxml=$PG_RESULTS/junit.xml
checks:
  visible: checks/visible
  hidden: checks/hidden
solution: solution/reference.patch
expected_paths: [src/payments/]   # optional, used for diff-scope feedback
hints:                    # progressive; each use is logged
  - Look at what happens when the provider times out but the charge succeeded.
  - The retry path never checks for an existing charge with the same key.
debrief:
  questions: debrief/questions.md
  focus: [debugging_method, test_quality, scope_judgment]   # coaching areas, unweighted
author: {name: Fran Delicado, github: <your-handle>}
content_license: CC-BY-4.0
provenance: handmade      # handmade | generated
```

### Execution contract

Every challenge runs in two separate phases. Mixing them is what made the earlier draft contradictory (`npm ci` with no network, sidecars with no network at all).

| Phase | When | Network | What runs |
| --- | --- | --- | --- |
| Build | `start` (cached by a hash of `environment/` + lockfiles) | External network allowed, so dependencies can be installed | `docker build` of `environment/Dockerfile`. For third-party packs, only after explicit consent (section 13). |
| Run | Every `check` | A per-check Docker network created with `internal: true`: the test container and its `services` reach each other, nothing reaches the internet | `test_command` against a copy of the workspace plus hidden checks |

Rules that follow from this:

- `test_command` must work with preinstalled dependencies only. If it needs to download anything, the challenge is invalid.
- Services are named by image and reachable by service name on the internal network (e.g. `postgres:5432`); credentials come from environment variables the challenge declares.
- Results are written as JUnit XML to `$PG_RESULTS/junit.xml`, the single results contract for every language.

### Verification contract

`patchground validate` runs these steps inside the challenge's containers and fails on the first one that doesn't hold:

1. The image builds from a clean checkout.
2. **Broken state fails:** the starting workspace fails at least one hidden check.
3. **Reference passes:** with `reference.patch` applied, all visible and hidden checks pass.
4. **Deterministic:** steps 2 and 3 give identical results across 3 runs (catches flaky tests).
5. **Editable-test tampering:** for supported pytest layouts, hidden outcomes remain unchanged
   after an empty diff and deletion/skipping of conventional editable test modules. Unsupported
   runners/layouts are explicitly unverified; see `docs/contracts/verification.md` for the limits.

`validate` writes `verification.json` with the image digest, run results and timestamps.

**What this does and doesn't establish.** Passing validation shows the challenge is internally consistent: the defect is observable by the checks and at least one solution passes them. It does not prove the ticket is complete, that the reference is the only correct solution, or that the exercise is realistic. Human review in official packs, plus at least one other person solving it, covers that.

### Reserved for later format versions

Not in v0.1, and the runner must not implement them yet: stages, `ai_policy: trap` (planted AI patches), `incident` and `ai-validation` types, and weighted rubrics.

### pack.yaml

```
spec_version: "0.1"
name: patchground-core
version: 0.1.0
description: Official curated challenges
challenges: [duplicate-charges-on-retry, flaky-cache-ttl]
```

## 7. CLI specification

The binary is `patchground` with the short alias `pgnd` (not `pg`, which developers read as Postgres). Every command supports `--json`. The Milestone column says when a command is built; nothing is implemented ahead of its milestone.

| Command | Purpose | Milestone |
| --- | --- | --- |
| `pgnd list [--type] [--lang] [--difficulty] [--tag]` | List installed challenges | M1 |
| `pgnd show <challenge>` | Metadata, timebox, AI policy; never the solution | M1 |
| `pgnd start <challenge> [--ai allowed\|forbidden] [--no-timer]` | Build the image (consent for third-party packs), create the workspace, print the ticket and path | M1 |
| `pgnd check` | Run visible and hidden checks on the internal network; report pass/fail per test | M1 |
| `pgnd reset` | Restore the workspace to its starting state (asks first) | M1 |
| `pgnd status` | Current session: elapsed time, last check result | M1 |
| `pgnd submit` | End the session and write the verified-outcomes report | M2 |
| `pgnd hint` | Reveal the next hint (logged) | M2 |
| `pgnd run -- <cmd>` | Run a command in the challenge container (start the app, query a service) | M2 |
| `pgnd new <id> --type debug --lang python` | Scaffold a challenge folder | M2 |
| `pgnd validate <path>` | Run the verification contract; non-zero exit on failure; CI-friendly | M0 basic, M2 complete |
| `pgnd doctor` | Check Docker, git, disk; print fixes | M1 |
| `pgnd sessions` / `pgnd report <session>` | Past sessions and their reports | M2 |
| `pgnd debrief --ai [--provider]` | AI coaching on a finished session | M3 experiment |
| `pgnd pack add <git-url>[@ref]`, `pack list\|update\|remove` | Install and manage packs, pinned by commit | M4 |
| `pgnd submit --transcript <file>` | Attach an AI-agent transcript as coaching evidence | M4 |
| `pgnd generate ...` | Generate a verified challenge from a supported repo | M3 as a separate script, M4+ in the CLI |
| `pgnd config set <key> <value>` | Defaults: provider, model, editor command | M3 |

**Example session (M1):**

```
pgnd start duplicate-charges-on-retry
# -> workspace at ~/patchground/sessions/2026-10-29-duplicate-charges-on-retry/
# open it in your editor, use Claude Code / Codex / nothing
pgnd check          # red: 2 hidden checks failing
pgnd check          # green: 14/14
```

## 8. Architecture

Patchground is a single Python CLI with nine internal modules. Docker does the isolation, git does the history, and the LLM is a pluggable leaf, never a dependency of the core loop.

&#91;embedded content: Patchground architecture · core modules and optional AI layer\]

The user only ever touches the workspace; everything above the dashed line works with no network and no API key.

### Components

| Module | Responsibility |
| --- | --- |
| `cli` | Typer commands, Rich output, `--json` mode. No business logic. |
| `spec` | Pydantic models for `challenge.yaml`, `pack.yaml`; JSON Schema export; loading and validation errors with file and line. |
| `packs` | Clone, pin (commit SHA), update and index packs under `~/.patchground/packs/`. |
| `sessions` | Create workspace, `git init` + initial commit, timer, append-only event log; snapshots in internal refs from M2. |
| `sandbox` | Build phase (network allowed, consent for third-party packs) and run phase (internal network only): build images, start services, run checks, enforce limits, collect results. The only module that talks to Docker. |
| `verify` | The verification contract from section 6; used by `validate`, `generate` and CI. |
| `report` | Deterministic metrics from the event log and git history. No LLM. |
| `ai` | Provider abstraction, prompt templates, debrief interviewer, generator calls. Imported lazily; the core works without it. |
| `generate` | Challenge generation pipeline (section 11); depends on `ai`, `sandbox`, `verify`. |

### Storage

```
~/.patchground/
├── config.toml           # defaults, provider, model; no keys stored by default
├── packs/<pack>@<sha>/   # installed packs, read-only
└── cache/                # image digests, verification results
~/patchground/sessions/<date>-<challenge>/
├── workspace/            # the user's git repo (open this in your editor)
└── .session/
    ├── session.json      # challenge id+version, start/end times, ai_policy
    ├── events.jsonl      # append-only log
    └── report.md         # written on submit / debrief
```

### Check execution

1. Copy the workspace into a fresh container from the built image (never bind-mount it writable) and add the hidden checks.
2. Create a per-check Docker network with `internal: true`; start the challenge's `services` on it. Nothing can reach the internet.
3. Run `test_command` with `PG_RESULTS=/results`, using only preinstalled dependencies.
4. Parse `/results/junit.xml`.
5. Append a `check_run` event with per-test results and duration; tear down the network and containers.
6. History-enabled sessions checkpoint captured editable inputs into private session-owned Git objects/internal refs, never the learner repository. Initial/completed-check capture respects applicable Git ignores and sensitive-file exclusions; uncertain filtering makes capture unavailable without invalidating checks. Native plumbing uses isolated temporary metadata without configured hooks/filters. See the owning sessions SPEC for the actual lifecycle and compatibility contract.

### Event log

Each line in `events.jsonl` is `{ts, type, data}`. Types in M1: `session_started`, `check_run`, `reset`. Added in M2: `submitted`, `hint_revealed`, `command_run`. Later: `transcript_attached`, `debrief_answer`.

The pristine starting workspace is kept read-only in `.session/original/`, so `reset` and the regression-test check never depend on snapshots.

Patchground never watches keystrokes or the screen. Optional extra evidence:

- Transcript attachment remains planned, not implemented. It would require explicit consent; transcript evidence is not proof of reasoning quality.
- Periodic snapshots are explicitly deferred. The implemented policy is initial/completed-check capture with `start --no-history` opt-out and read-only `history`; no restore command.

## 9. Feedback: verified outcomes, then coaching

The report has two parts that are never mixed: facts Patchground can verify, and coaching it can only offer. There is no overall score. Git history alone can't distinguish careful investigation from pasting an agent's answer, so the report never pretends it can.

### Part 1: verified outcomes (deterministic, no AI)

| Outcome | How it is established | Milestone |
| --- | --- | --- |
| Checks passed | Per-test results from JUnit XML, e.g. 12/12 | M1 |
| **Regression test verified** | The user's new or changed tests are run against `.session/original/`: they must fail there and pass on the final workspace | M2 |
| Tests deleted or weakened | Removed test files, functions or assertions flagged | M2 |
| Diff scope | Files and lines changed; files outside `expected_paths`, if declared | M2 |
| Time and effort | Total time vs timebox, number of checks, hints used | M2 |

Each outcome is stated as a fact ("Verified: fails before, passes after"), never as a grade.

### Part 2: coaching (optional, AI, M3 experiment)

`pgnd debrief --ai` reads the ticket, `questions.md`, the verified outcomes, the final diff and the check history, then:

1. **Interviews.** Asks 3–6 questions one at a time, generated from the final changes, with adaptive follow-ups: "Why fix it here rather than upstream?" "How do you know this doesn't break refunds?"
2. **Observes.** For each `focus` area, either writes feedback that cites evidence (a file and line, a check number, an answer) or says **"Not observed"**. Example: AI usage and validation is "Not observed" unless a transcript was attached.
3. **Coaches.** Two or three concrete improvements and suggested next challenges.

**Guardrails:** outcomes from Part 1 cannot be overridden by the LLM; any observation without evidence is rejected and regenerated; low temperature; the full prompt and context are saved in `.session/` for inspection.

**The M3 experiment's success test:** run it on 10 or more real sessions from M2 and ask the users whether the questions felt like a real interviewer and taught them something. If not, it stays out of the product.

### Example report

```
duplicate-charges-on-retry · 38 min of 45 · 4 checks · 1 hint

VERIFIED
  Checks             12/12 passing
  Regression test    Verified: fails before, passes after
  Diff scope         2 files, +41 −6, all inside src/payments/

COACHING (AI, optional)
  Debugging method   Reproduced the timeout before changing code (check #1 red on the new test)
  Test quality       Test covers the retry path; no case for a provider error after success
  AI usage           Not observed: no transcript provided
```

### What verification is not

Hidden tests live on the user's machine, so a determined user can read them. Patchground is a practice tool on the honor system, not a proctored assessment. Anti-cheating is out of scope; the CLI simply never prints hidden test sources.

## 10. BYOK provider layer

The `ai` module exposes one small interface; every AI feature goes through it, and the core never imports a provider SDK directly.

Nothing before the M3 experiments may depend on this module. Start with one provider (Anthropic) plus Ollama; add the others only if the experiments go well.

```
class Provider(Protocol):
    name: str
    def complete(self, messages: list[Message], *, schema: type[BaseModel] | None = None,
                 temperature: float = 0.2, max_tokens: int = 4096) -> Completion: ...
    def estimate_tokens(self, messages: list[Message]) -> int: ...
```

**Supported providers, in order:**

1. **Anthropic** (Claude) via its SDK.
2. **OpenAI-compatible** endpoint: covers OpenAI, OpenRouter, Groq, Together, LM Studio and vLLM with one adapter and a `base_url`.
3. **Ollama** (local, keyless) for fully offline AI features.
4. **CLI agents as providers (later):** shell out to `claude -p` or `codex exec` so users can reuse a subscription they already pay for instead of an API key.

**Configuration:**

```
# ~/.patchground/config.toml
[provider]
default = "anthropic"

[provider.anthropic]
model = "<model id>"
api_key_env = "ANTHROPIC_API_KEY"   # keys are read from env vars, never written to disk

[provider.ollama]
base_url = "http://localhost:11434"
model = "<local model>"
```

**Rules:**

- Before the first AI call in a session, show the provider, model, estimated tokens and exactly which files will be sent; require confirmation (skippable with `--yes`).
- Send the minimum context: ticket, diffs, selected files and test output, not the whole repository.
- Structured outputs (debrief scores, generator proposals) use the schema argument and are validated; on validation failure, retry up to 2 times, then fail clearly.
- Prompts live as versioned template files in the repo (`patchground/ai/prompts/*.md`), not inline strings, so they can be reviewed and evaluated.

## 11. Challenge generation

`pgnd generate` turns a repository from a small supported set into a verified challenge using the user's own AI. It is the most uncertain part of the concept, so it is tested early as a standalone experiment and only becomes a CLI command if the experiment works.

**The M3 experiment.** One small Python repository with a trustworthy test suite, a script in `experiments/generate/`, no generalized framework. The model introduces a realistic bug, writes the issue as a ticket and produces the reference fix; the script validates it with the contract from section 6. Then a human who hasn't seen the bug solves it. Success means most generated challenges pass validation and the solver rates them as realistic and non-trivial.

**Supported repositories (v0).** Pure-Python projects with a pytest suite that passes deterministically, no external services, a permissive license, and a test run under 2 minutes. Other ecosystems, services and private repos are out of scope until this works.

**Example request:** "Give me an intermediate debugging challenge involving async programming in this Python project. Don't tell me where the issue is."

### Pipeline

1. **Ingest.** Take a repo from the supported set at a pinned commit; detect language, package manager and test command; build the container.
2. **Baseline.** Run the full test suite. Abort unless it passes deterministically 3 times. A repo with failing or flaky tests cannot produce a trustworthy challenge.
3. **Map.** Build a compact repo map (files, symbols, test-to-source links, coverage if available) so the model can pick code that tests actually exercise.
4. **Propose.** The model returns a structured proposal: target files, the defect (or feature) as a patch, a realistic ticket written from the user's point of view (symptoms, not the cause), difficulty rationale and hints.
5. **Apply and prove broken.** Apply the patch; at least one existing test must now fail. If none does, the model writes a new hidden test that fails on the mutated code and passes on the original; that test is verified both ways.
6. **Prove solvable.** Reverting the patch (the reference solution is the reverse patch) makes every check pass again, 3 runs in a row.
7. **Quality gates.** Reject proposals where: the bug is a syntax or import error; the diff is trivially visible (comments like "bug here", renamed symbols); the failing test name reveals the location; or the change touches tests only.
8. **Package.** Write a standard challenge folder (section 6) with `provenance: generated`, the model and prompt version, and `verification.json`. It is then indistinguishable from a handmade challenge.

Retry budget: up to 5 proposals per request, then fail with the reasons each was rejected.

**Feature and review challenges** use the same pipeline in reverse: remove a cohesive piece of functionality (feature) or generate a plausible PR with planted flaws (review); the original code is the reference.

**Evaluating the generator itself.** Keep a small benchmark: a fixed set of repos and requests, with metrics for verification pass rate, quality-gate rejection reasons, and a human rating of realism on a sample. Run it whenever prompts or models change. Public coding benchmarks have shipped a significant share of tasks with defective specs or tests, so this check is not optional.

## 12. Community and distribution

Packs are plain git repositories; GitHub is the registry until there is real demand for a website.

**Packs:**

- **`patchground-core`** is the official, curated pack maintained in the main org. It is the quality bar.
- **Community packs** are any git repo with a valid `pack.yaml`, installed with `pgnd pack add github.com/<user>/<pack>`. They are untrusted: pinned by commit, labelled "unofficial", and nothing from them is built or run without explicit consent.
- **Private packs** work the same way, for teams training their own engineers on a stripped copy of their codebase.

**Contributing a challenge:**

1. `pgnd new <id> --type debug --lang python` scaffolds the folder.
2. The author writes the workspace, ticket, checks, solution and optional debrief questions.
3. `pgnd validate .` must pass locally.
4. The PR runs a reusable GitHub Action (`patchground/validate-action`) that runs `validate` on changed challenges.
5. A maintainer reviews realism and difficulty; at least one other person solves it before merge.

**Quality signals per challenge (later):** solve rate, median time, and a 1–5 user rating, all submitted opt-in and anonymously.

**Website (much later):** a static catalog generated from pack indexes (browse, filter, copy the `pgnd start` command), then optional opt-in ratings. No accounts or hosted sandboxes until the CLI has real users. A hosted, no-setup version is the open-core path if money ever becomes a goal.

## 13. Security and privacy

**The guarantee, stated honestly:** Patchground never intentionally executes challenge commands on the host. Official packs are reviewed; third-party packs are untrusted and require explicit consent before their environments are built or run.

What Patchground cannot control: the user opens the workspace in their own editor, where package scripts, dev servers or an AI agent with shell access may run code. The docs must say this plainly, and recommend that untrusted challenges are opened in a containerized dev environment (a dev container is a candidate future feature).

### Trust levels

| Source | Trust | Before build/run |
| --- | --- | --- |
| `patchground-core` (official) | Reviewed by maintainers | No prompt |
| Local challenge the user authored | The user's own code | No prompt |
| Third-party pack | Untrusted | Show the Dockerfile, services and test command; require a yes per pack version |
| Generated challenge | Derived from a repo the user chose | Same as the source repo's trust |

Building an image from an untrusted Dockerfile is itself security-sensitive, which is why consent happens before the build phase, not only before checks.

### Container defaults

- **Build phase:** external network allowed (to install dependencies), no host mounts, no Docker socket, build-time limits.
- **Run phase:** per-check internal network only (`internal: true`); no internet egress; services reachable only by name on that network.
- Non-root user, read-only root filesystem, writable `/workspace` and `/results` only.
- CPU, memory, PID and wall-clock limits (defaults: 2 CPUs, 2 GB, 512 PIDs, 10 minutes per check).
- Dropped Linux capabilities and `no-new-privileges`.

### Supply chain

- Packs are pinned to a commit SHA; `pack update` shows a change summary and asks for consent again.
- Images are recorded by digest in `verification.json`; a mismatch triggers re-validation.
- Manifest commands run only inside containers, never through the host shell.

### Privacy

- No telemetry by default. Community stats (section 12) are opt-in, anonymous and never include code.
- API keys come from environment variables and are never logged or written to session files.
- Snapshots (from M2) skip ignored and sensitive files and live in internal refs, never on the user's branches.
- Every AI call's full payload is saved in `.session/` so users can audit what was sent.
- Generating from a private repo warns that code will be sent to the configured provider and offers Ollama instead.

## 14. Roadmap

Implementation status below is reconciled with the M1 local prototype. The contracts and module
SPECs remain authoritative; future roadmap items are not claims of implemented behavior.

The order is chosen to answer the riskiest question first: do developers enjoy practicing with realistic challenges in their own IDE, and can someone else author one? No infrastructure is built before that has an answer. No dates are set, since this is a side project next to work and the thesis.

### M0 — Minimal spec

- [x] Repo, Apache-2.0 license, `uv` project, CI (lint, type check, tests)
- [x] Pydantic models for single-stage `challenge.yaml` v0.1 and `pack.yaml`; JSON Schema exported to `schema/`
- [x] Execution contract written in `docs/contracts/execution.md`
- [x] Basic `pgnd validate`: schema check, image builds, broken state fails, reference passes

### M1 — Playable prototype

- [x] Local `list`, `show`, `start`, `check`, `reset`, `status`, `doctor`
- [x] Runner with build and run phases, internal network, JUnit parsing
- [x] Python `debug` example (`pagination-last-page`) with a ticket and validation coverage
- [ ] Fresh-user trial: independently install, discover, solve and reset; assess challenge quality

Multi-container services are explicitly deferred beyond this single-container prototype. Local
listing does not install packs or resolve IDs. See `docs/first-session.md` for the trial checklist.

* **Done when:** a fresh user installs with one command and completes the challenge in their own editor without asking Fran anything.

### M2 — External validation

- [x] Two more Docker-validated challenges: duplicate charges on retry and cache expiry
- [x] `submit` and immutable verified-outcomes reports, including bounded pytest regression evidence
- [x] Determinism validation: three runs per workspace variant, comparing per-test evidence
- [x] Bounded pytest editable-test tampering probes, with unsupported adapters explicitly unverified
- [x] `pgnd new` runnable Python/debug scaffold with packaged assets
- [ ] Broader validation adapters as needed
- [x] `hint`, `run`, `sessions`, `report`; private initial/check checkpoint refs and read-only `history`
- [ ] Give it to about 10 developers preparing for interviews and watch them install, read the ticket, solve and finish
- [ ] Ask one developer who isn't Fran to author and validate a challenge from the docs alone

* **Gate:** continue if most testers finish without help, at least some ask for another challenge, and the external author succeeds. If authoring is painful, fix it before anything else: the community model depends on it.

### M3 — Two experiments (independent of each other)

- [ ] **AI debrief:** `debrief --ai` with Anthropic and Ollama, run on real M2 sessions; keep it only if users find the questions useful (section 9).
- [ ] **Generator:** a script in `experiments/generate/` on one supported Python repo; keep going only if generated challenges validate and a human rates them realistic (section 11).

### M4 — Expand based on what worked

Pick from, in the order feedback demands: Git-distributed packs (`pack add` and trust prompts), `validate-action` and the contribution guide, TypeScript support, more challenge types, transcripts as coaching evidence, the generator as a CLI command, and a design for stages that works with any valid earlier solution.

### Later, only with demand

A static catalog website (on frandeli.dev or its own domain), opt-in anonymous ratings, a dev-container option for untrusted challenges, and possibly a hosted mode.

## 15. Tech stack and repo layout

Python 3.12+, packaged with `uv` and installable via `uv tool install patchground` or `pipx install patchground`.

| Concern | Choice | Why |
| --- | --- | --- |
| CLI | Typer + Rich | Typed commands, good help output, nice terminal reports |
| Schemas | Pydantic v2 | Validation errors, JSON Schema export, structured LLM outputs |
| Containers | Docker SDK for Python (Podman via its Docker-compatible socket) | Isolation without writing a sandbox |
| Git | `git` subprocess with a thin wrapper | Fewer surprises than a library; git is already required |
| Test results | JUnit XML parser (`junitparser`) | One contract for every language |
| AI | `anthropic`, `openai` SDKs as optional extras (`patchground[ai]`) | Core installs without AI deps |
| Tests | pytest, with Docker-backed integration tests marked `@pytest.mark.docker` |  |
| Lint / types | ruff, mypy (strict on `spec`, `verify`, `report`) |  |
| Docs | MkDocs Material, the format spec as its centerpiece |  |

**Repositories:**

- `patchground/patchground`: the CLI, the spec, schemas and docs.
- `patchground/patchground-core`: the official challenge pack.
- `patchground/validate-action`: the GitHub Action (M4).

**License:** Apache-2.0 for the CLI, to keep adoption friction low. Each challenge declares its own `content_license` (default CC-BY-4.0); code inside a challenge workspace keeps the license of the project it came from.

**CLI repo layout:**

```
patchground/
├── src/patchground/
│   ├── cli/              # one file per command group
│   ├── spec/             # models.py, loader.py, schema_export.py
│   ├── sessions/         # workspace.py, events.py, timer.py
│   ├── sandbox/          # build.py, run.py, network.py, limits.py, junit.py
│   ├── verify/
│   ├── report/           # verified outcomes (M2)
│   ├── packs/            # (M4)
│   └── ai/               # providers/, prompts/*.md, debrief.py (M3)
├── experiments/
│   └── generate/         # M3 generator experiment, outside the package
├── schema/               # exported JSON Schemas, versioned
├── templates/            # scaffolds for `pgnd new`
├── examples/             # 1–2 tiny challenges used by the test suite
├── tests/
├── docs/
│   ├── spec.md           # this document: vision, principles, roadmap
│   └── contracts/        # the rules agents implement against, one per area
│       ├── challenge-format.md
│       ├── execution.md
│       ├── verification.md
│       ├── cli.md
│       ├── feedback.md
│       └── security.md
├── AGENTS.md             # short: see section 17 (CLAUDE.md can point to it)
└── pyproject.toml
```

## 16. Open questions and risks

### Open questions

- [ ] **Name availability:** check the GitHub org, PyPI, npm and domains; patchground.com was reportedly listed for sale, so `.dev` or a subdomain of frandeli.dev may be the realistic option.
- [ ] **Windows:** support via WSL2 + Docker Desktop only, or native? (Assumed WSL2 only.)
- [ ] **Session location:** `~/patchground/sessions/` or the current directory?
- [ ] **Stages:** what transition model lets stage 2 work on top of any valid stage-1 solution? Needed before stages enter the format.
- [ ] **Dev containers:** should `start` optionally open the workspace in a dev container, so untrusted challenges never run in the user's own environment?
- [ ] **System design challenges:** in scope later, or a separate tool? They don't fit the "tests verify it" model.
- [ ] **Transcript formats:** which agent exports to parse first (Claude Code, Codex, Cursor)?
- [x] **License:** decided, Apache-2.0 for the CLI, per-challenge content licenses (section 15).

### Risks

| Risk | Mitigation |
| --- | --- |
| Content quality: mediocre challenges kill the project regardless of the runner | Curated core pack first; a second solver per challenge; external-author test in M2; ratings later |
| Generated bugs are trivial or unrealistic | Verification contract, quality gates, generator benchmark |
| Docker setup friction narrows the audience | Acceptable: the audience is developers; `doctor` gives exact fixes |
| Incumbents add a "debugging track" | Don't assume they won't copy; compete on trusted quality, easy local runs and low-friction authoring |
| No revenue | Fine: the goals are career, portfolio and reputation; hosted open-core remains possible |
| Limited personal time | M1 is one challenge and one runner; the M2 gate comes before any AI work, so little is sunk if the idea doesn't land |
| Heavy LLM costs for users | Debrief sends minimal context; Ollama path; token estimate shown before every call |

## 17. Instructions for the coding agent

`AGENTS.md` stays short: what the project is, the current milestone, hard rules, and where the detailed contracts live. Agents load the contract for the module they are touching instead of the whole spec.

**Contract docs to create from this spec** (in `docs/contracts/`):

| File | Source sections | Covers |
| --- | --- | --- |
| `challenge-format.md` | 6 | Layout, `challenge.yaml` v0.1 fields, reserved keys, `pack.yaml` |
| `execution.md` | 6, 8, 13 | Build vs run phases, internal networks, limits, JUnit contract |
| `verification.md` | 6 | The `validate` steps and what they do and don't establish |
| `cli.md` | 7 | Commands, flags, `--json` output, milestone per command |
| `feedback.md` | 9 | Verified outcomes vs coaching, no overall score |
| `security.md` | 13 | The guarantee, trust levels, consent, privacy |

**AGENTS.md:**

```
# Patchground

Open-source, local-first CLI (`patchground`, alias `pgnd`) for practicing real software
engineering. Users solve challenges in their own editor with their own AI; Patchground
runs verification in Docker and reports verified outcomes.

Background: docs/spec.md. Rules you implement against: docs/contracts/*.md
(read the one for the module you are changing). If a contract and the code disagree,
or a contract is ambiguous, stop and ask.

## Current milestone: M1 (playable prototype)
Build only: list, show, start, check, reset, status, doctor; the runner with build and
run phases; one Python debug challenge in examples/ that passes `pgnd validate`.
Do NOT build: stages, scoring, reports, snapshots, hints, packs, AI, generator, web UI.

## Hard rules
- Challenge commands run only in containers via sandbox/. Never through the host shell.
- Build phase may use the network; run phase uses an internal network only.
- Third-party packs: ask for consent before building or running anything from them.
- Never copy solution/ or hidden checks into the workspace; never print hidden tests.
- Never modify the user's git HEAD, branches, index or staging area.
- Never write API keys to disk or logs.
- Correctness comes from tests only. No overall scores.
- Core must work without the [ai] extra installed.
- Use the glossary terms exactly: challenge, pack, session, workspace, check, debrief.

## Conventions
Python 3.12+, uv, Typer, Rich, Pydantic v2, ruff, mypy (strict on spec/ and verify/).
Every command supports --json. Manifest errors name the file and line.
Unit tests per module; Docker integration tests marked @pytest.mark.docker.
Work in small PR-sized steps; run lint, types and tests before calling a step done.

## Definition of done for M1
On a fresh machine with Docker and git: install the CLI, `pgnd list`, `pgnd start` the
example challenge, fix it in an editor, `pgnd check` to green, with no network after the
image build and no API key.
```

At each new milestone, update only the "Current milestone" block and add the relevant contract docs.

## Sources

From search results gathered on 29 Oct 2026; the ChatGPT-sourced competitors in section 3 are not listed here because they were not re-checked.

- [CodeSignal launches agentic coding assessments (PR Newswire via Owler)](https://www.owler.com/reports/owler/Press-Release--CodeSignal---CodeSignal-Launches-Industry-First-Agentic-Coding-Assessments-for-AI-Era-Engineering-Hiring/1775178133271)
- [CoderPad tech interview 2026 format (Interview Query)](https://www.interviewquery.com/p/coderpad-tech-interview-2026-format)
- [Byteboard profile (Parse)](https://parse.gl/brands/byteboard-dev)
- [Intervu / interview-os (GitHub)](https://github.com/vvknyn/interview-os)
- [InterviewLab (GitHub)](https://github.com/javedshaik1228/interviewlab)
- [Interviewa (GitHub)](https://github.com/sh78ba/Interviewa)
- [The post-LLM coding interview format (techinterview.org)](https://www.techinterview.org/post/3233474920/post-llm-coding-interview-format/)
- [Anti-LeetCode interview formats (techinterview.org)](https://www.techinterview.org/post/3233474683/anti-leetcode-interview-formats/)
