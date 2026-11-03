---
id: patchground-architecture
type: architecture-design
status: draft
title: Patchground — Architecture
parent: patchground-goal
---

# Architecture

Patchground is a single Python package (`src/patchground/`) exposed as one CLI. Docker does the
isolation and git does the history. The shipped package has no AI coaching or generation modules;
the optional guide skill runs in the user's own assistant, outside the CLI.
The user only ever touches the workspace; everything else runs with no network (after the image
build) and no API key.

## Topology

```mermaid
flowchart TD
  cli --> authoring & packs & sessions & verify & report & sandbox
  authoring --> spec & runner_assets
  verify --> runner_assets
  automation --> packs & verify & spec & safeio
  packs --> spec & safeio
  sessions --> spec & sandbox & packs & safeio
  verify --> spec & sandbox & packs & safeio
  report --> sessions & sandbox & verify
  sandbox --> spec
  sandbox ==> docker[(Docker / Podman)]
  sessions ==> git[(git subprocess)]
```

| Module | Owns | Spec |
| --- | --- | --- |
| `cli` | Commands, terminal and `--json` output, consent prompts. No business logic. | `patchground-cli` |
| `authoring` | Safe local scaffolding from packaged runnable templates; no execution. | `patchground-authoring` |
| `automation` | Committed changed-challenge selection and safe aggregate results for the in-repository Action. | `patchground-automation` |
| `runner_assets` | Canonical portable container harness and locked toolchain bytes; no host execution. | `patchground-runner-assets` |
| `spec` | Manifest models, loading, schema export. Depends on nothing internal. | `patchground-spec` |
| `packs` | Pinned distribution, immutable content, resolution and execution consent. | `patchground-packs` |
| `safeio` | Shared descriptor-safe filesystem access and Git executable selection. | `patchground-safeio` |
| `sessions` | Session lifecycle, workspace repo, event log, check orchestration. | `patchground-sessions` |
| `sandbox` | Every interaction with the container engine. | `patchground-sandbox` |
| `verify` | The verification contract run against a challenge folder. | `patchground-verify` |
| `report` | Immutable verified outcomes from captured files, events and container probes. | `patchground-report` |
| `registry/` | Public index of community packs: scheduled discovery by GitHub topic, re-validation in CI, `index.json`/`status.json`. A script beside the package, not inside it. | `patchground-registry` |
| `ai` | Optional AI coaching. Deferred from launch after a bounded local evaluation (`docs/evaluations/ai-debrief-smoke.md`); not in the package. | — |
| `generate` | Challenge generation experiment. Deferred from launch; not implemented. | — |

Edges not drawn above are forbidden. In particular: nothing below `cli` imports `cli`; nothing in the
core imports `ai` or `generate`; only `sandbox` imports the Docker SDK; only `sessions` runs git on
workspaces (others read git data through `sessions`), `packs` runs isolated Git retrieval and raw
object inspection without loading source configuration, and `verify` runs only `git apply` on a
throwaway copy of a challenge's `workspace/` (never a repo the user owns, never with repository config a challenge could supply). `report` uses
`verify` only for shared pure pytest/TypeScript recognition and static-analysis primitives; submission execution
still goes through `sandbox`, and sessions never imports report. `cli` reaches `sandbox` only for `doctor`'s engine probe.

## Cross-cutting decisions

- **The contracts are the rules.** Behavior that spans modules is fixed in the contract specs under
  `docs/contracts/`; modules implement them and never restate them:
  `patchground-contract-challenge-format`, `patchground-contract-execution`,
  `patchground-contract-verification`, `patchground-contract-cli`, `patchground-contract-feedback`,
  `patchground-contract-security`.
- **Two-phase execution.** Building an image may use the network; running checks never does. See
  `patchground-contract-execution`.
- **Runtime TypeScript, not type checking.** A pinned Vitest harness normalizes identities and
  withholds JUnit on runner-wide faults without changing global sandbox exit semantics. Shared
  Tree-sitter parsing supplies bounded tampering/regression evidence without importing authored
  code. Canonical `runner_assets` bytes are copied into portable authored environments; neither
  `authoring` nor `verify` executes those assets on the host.
- **AI stays outside the shipped core.** The `[ai]` extra is empty. Coaching and generation are
  deferred, and their historical experimental design is not an implemented boundary. Any revival
  requires an accepted design and must preserve core independence and the security contract's
  consent requirements. The repository guide skill uses the user's external assistant and its
  permissions; it does not make model calls through Patchground.
- **Git through a thin subprocess wrapper,** not a library: git is already required and the CLI's
  behavior is easier to predict.
- **The user's git state is sacred.** Patchground never changes the workspace's HEAD, branches, index
  or staging area. Checkpoint objects and `refs/patchground/*` live in private session-owned Git
  storage, built through isolated temporary indexes/repositories. Ignore configuration is read only
  as data; configured tools, hooks and filters never execute. Initial/check checkpoints are optional;
  failure cannot invalidate test evidence. There is no periodic capture or snapshot restoration.
- **Glossary terms are exact.** Identifiers, messages and docs use the terms in `patchground-goal`.

## Storage

```
~/.patchground/
├── registry.json         # pinned versions, active revision and exact-version consent
└── packs/<pack>@<sha>/    # installed packs, read-only
~/patchground/sessions/<date>-<challenge>/
├── workspace/            # the user's git repo
└── .session/             # session.json, events.jsonl, original/, submission/
```

Sessions live under `~/patchground/sessions/` unless `PATCHGROUND_SESSIONS_DIR` names another
absolute directory; the layout of `.session/` is owned by `patchground-sessions`. The wheel also
carries the curated `examples/` as a read-only built-in catalog (`patchground/catalog/`), owned by
`patchground-packs` resolution.

## Platforms

macOS and Linux with Docker (or Podman through its Docker-compatible socket) and git. Windows only
through WSL2 + Docker Desktop; `pgnd doctor` points Windows users there.

## Public site boundary

`patchground.dev` is a public documentation and challenge-catalog surface, not a hosted runner.
Challenge execution, session state and verified outcomes stay local. Published catalog data is an
allowlist of public challenge metadata and tickets, never session data, hidden checks, reference
solutions or credentials. The standalone `web/` module (`patchground-web`) owns the product-first
static homepage (an Astro build with no runtime dependencies), with CLI installation, real-world practice, public guides and challenge tickets. It has no dependency on the CLI; its catalog is
rendered at build time from an allowlist of public `challenge.yaml` fields plus the community index in
`registry/index.json` (see `patchground-web`, `patchground-registry`), and its build emits only
the public pages, `catalog.json` and hashed assets. Community packs reach the site by *publish and appear*: the
author tags their repository, CI re-validates it, no pull request (`patchground-registry`). The public
site is served by Cloudflare Workers static assets configured in `wrangler.jsonc`. DNS, production
deployment, package publication and releases still require approval at publication.

## Repositories

- `franndeli/patchground` — this repo: the CLI, the format, schemas (`schema/`), scaffolds
  (`src/patchground/authoring/templates/`), test challenges (`examples/`), docs, and the reusable
  validation Action (`action.yml`, `patchground-automation`). The Action uses the same verifier with
  explicit execution consent and disposable committed inputs, never mutating the checkout.
The curated catalog ships from `examples/` inside this repository and wheel; a separate official-pack
repository is not required. The validation Action is versioned here with the CLI, superseding the
separate-repository plan.

## Testing

Unit tests per module; tests that need a container engine are marked `@pytest.mark.docker`, and CI
sets `PATCHGROUND_REQUIRE_DOCKER=1` so they fail rather than skip without an engine. ruff for lint,
mypy strict on `spec`, `verify`, `report`, `sessions`, `authoring` and `sandbox` (the safety boundary). The challenges in
`examples/` must pass `pgnd validate` in CI; their `verification.json` is gitignored, because a
locally built image id means nothing on another machine and CI re-validating every push is the
proof. Broken challenges, one per failing step, live in `tests/fixtures/`.
