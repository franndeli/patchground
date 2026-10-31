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
| `patchground-core` (official) | Reviewed by maintainers | No prompt |
| A local challenge path the user authored | The user's own code | No prompt |
| Third-party pack | Untrusted, labelled "unofficial" | Show the Dockerfile, services and test command; require a yes per pack version |
| Generated challenge | Same as the source repo | Same as the source repo |

Consent happens before the **build** phase, because building an untrusted Dockerfile is itself
sensitive. Container isolation defaults live in `patchground-contract-execution`.

## Supply chain

- Packs are pinned to a commit SHA; `pack update` shows a change summary and asks for consent again.
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
