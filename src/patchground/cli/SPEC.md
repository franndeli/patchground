---
id: patchground-cli
type: module-design
status: draft
title: "Module: cli"
parent: patchground-architecture
depends-on: [patchground-packs, patchground-sessions, patchground-verify, patchground-report, patchground-sandbox, patchground-authoring]
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
- `doctor`: assembles checks from `sandbox` engine probing and the `sessions.diagnostics` Git and
  disk probes, and prints the exact fix for each failure (platform-specific; WSL2 on Windows). It
  reports every check (`{"healthy", "checks": [{name, status, detail, problem, fix}]}` under
  `--json`), exits `0` when all pass and `2` otherwise, and never builds or runs a challenge. The
  disk check uses a 1 GiB free-space baseline at the sessions root (or its nearest existing parent);
  that is a floor, not a guarantee an image build fits. Paths under home display as `~`.
- `new`: calls `authoring.create_challenge`; renders the new relative path and validation next
  step, or JSON `{id, path, type, language, files}`. It never runs the new challenge.
- `submit`/`report`: call the report module and render its versioned facts as JSON or Markdown
  text. Submit exits `1` for nonpassing final checks; reading that same report succeeds. Status
  displays active/submitted state; no CLI path reopens a closed attempt.
- `hint`, `sessions`, `history` and `run`: delegate to session-owned practice/history APIs.
  Run options precede a required `--`; everything afterward is literal container argv. Usage
  failures do not echo arguments. Bounded command output uses literal Rich text, never markup;
  human output always labels it as a tail and warns that container edits are discarded.
  Nonzero/limited commands and listings with invalid candidates exit `1`; infrastructure exits `2`.
  `start --no-history` disables new-session checkpoints; start/check display unavailable history
  separately from correctness. History is read-only and available after submission.
- Pack management and installed discovery delegate to packs. Consent renders complete recipes as
  literal escaped text, binds interactive retries to the reviewed identity, and never prompts in
  JSON mode. Raw reference strings preserve explicit local-path syntax. JSON escapes control
  characters; unexpected validation/transport failures never expose raw tool output.
- Mapping domain errors to messages and exit codes; manifest errors keep their file and line. Any
  unexpected exception still ends as one `internal` error (exit `2`, one JSON document under
  `--json`), never a traceback that reads as exit `1`.

## Boundary

May import every core module. Imports `ai` (and later `generate`) only inside the AI commands, so a
core install without `patchground[ai]` runs every other command. Never talks to Docker or git directly; touches `sandbox` only for `doctor`'s probe.
