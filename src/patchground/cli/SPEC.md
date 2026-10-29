---
id: patchground-cli
type: module-design
status: draft
title: "Module: cli"
parent: patchground-architecture
depends-on: [patchground-packs, patchground-sessions, patchground-verify, patchground-report, patchground-sandbox]
implements: [patchground-contract-cli]
---

# cli

The Typer application behind `patchground` / `pgnd`: argument parsing, Rich rendering, `--json`
output, prompts. It implements `patchground-contract-cli` and holds no business logic — each command
resolves inputs, calls one module entry point, and renders the result.

## Owns

- One file per command group; a shared renderer so every command's result has both a human and a
  `--json` form from the same data.
- All interactive prompts: consent for untrusted packs (what to show comes from `packs`), reset
  confirmation, the AI payload preview. `--yes` answers them; `--json` never prompts.
- `doctor`: assembles checks from `sandbox` engine probing, git and disk, and prints the exact fix
  for each failure.
- Mapping domain errors to messages and exit codes; manifest errors keep their file and line. Any
  unexpected exception still ends as one `internal` error (exit `2`, one JSON document under
  `--json`), never a traceback that reads as exit `1`.

## Boundary

May import every core module. Imports `ai` (and later `generate`) only inside the AI commands, so a
core install without `patchground[ai]` runs every other command. Never talks to Docker or git directly; touches `sandbox` only for `doctor`'s probe.
