---
id: patchground-contract-security
type: architecture-design
status: draft
title: "Contract: security and privacy"
parent: patchground-architecture
---

# Security and privacy

**The guarantee, stated honestly:** Patchground never intentionally executes challenge commands on the
host. Official packs are reviewed; third-party packs are untrusted and need explicit consent before
their environments are built or run.

What it cannot control: the user opens the workspace in their own editor, where package scripts, dev
servers or an agent with shell access may run code. The docs say so plainly and recommend opening
untrusted challenges in a containerized dev environment.

## Trust levels

| Source | Trust | Before build/run |
| --- | --- | --- |
| Installed pack, including one named `patchground-core` | Unofficial until an owner-controlled official origin is established | Exact-version consent |
| A local challenge path the user authored | The user's own code | No prompt |
| Built-in catalog challenge (curated `examples/` shipped inside the installed CLI) | First-party, same origin and review as the CLI code that runs it | No prompt; never written to |
| Third-party pack | Untrusted, labelled "unofficial" | Show the Dockerfile, services and test command; require a yes per pack version |
| Generated challenge | Same as the source repo | Same as the source repo |
| Community pack in the public registry | Unofficial; *verified* means it passed `pgnd validate` in Patchground CI at one commit (`patchground-registry`) | CI crawler consents for itself in an isolated read-only job; users still get the per-version prompt on install |

Consent happens before the **build** phase, because building an untrusted Dockerfile is itself
sensitive. Container isolation defaults live in `patchground-contract-execution`.

## Supply chain

- Packs bind source, commit and captured content identity. Names never establish official trust.
  `pack update` reviews changes and complete recipes before activating a changed version; consent
  never silently carries to new content. Managed paths cannot bypass this gate. Installation and
  read-only inspection do not execute challenge commands; core start/validate enforce consent.
- Public HTTPS and committed local Git data are supported; credential-bearing URLs and private
  authentication are refused. Source Git configuration, hooks and filters never execute.
  Import and preview limits and integrity handling belong to `patchground-packs`.
- Images are recorded by digest in `verification.json`; a mismatch triggers re-validation.

## Privacy

- No telemetry by default. Any community stats are opt-in, anonymous and never include code.
- API keys are read from environment variables only; never written to config, logs or session files.
- Checkpoint history skips all applicable Git-ignored files and a sensitive-file list
  (`.env*`, `*.pem`, `*.key`, `id_*`). If applicable ignore rules cannot safely be established,
  capture is unavailable, not permission to retain potentially ignored files. Objects/internal
  refs live in private session-owned Git storage, never on the user's branches or index. This
  filtered history differs from immutable submission evidence, which includes ordinary ignored
  checked files to faithfully preserve verification input.
- Diagnostic commands receive only editable-workspace copies, never frozen hidden checks. Their
  sanitized output tail may be displayed explicitly, but command arguments/output are not written
  to session events. Raw verification logs remain private. Host environment secrets are not
  forwarded to containers.
- Before the first AI call in a session, show provider, model, estimated tokens and exactly which files
  will be sent, and require confirmation (`--yes` skips). Send the minimum context: ticket, diffs,
  selected files, test output — never the whole repository.
- Every AI call's full payload is saved in `.session/` for audit.
- Generating from a private repo warns that code goes to the configured provider and offers Ollama.
- Anti-cheating is out of scope: hidden tests are on the user's disk; the CLI simply never prints them.
