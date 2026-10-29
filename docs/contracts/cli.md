---
id: patchground-contract-cli
type: architecture-design
status: draft
title: "Contract: CLI"
parent: patchground-architecture
depends-on: [patchground-contract-execution, patchground-contract-security, patchground-contract-feedback]
---

# CLI

The binary is `patchground` with the alias `pgnd` (not `pg`, which developers read as Postgres).

## Global rules

- Every command supports `--json`: exactly one JSON document on stdout, nothing else; human output
  (Rich) otherwise. Prompts never appear in `--json` mode — a command that needs consent fails with a
  clear error unless `--yes` is given.
- Manifest errors name the file and line.
- The CLI never prints the reference solution or hidden test sources.
- Exit codes: `0` success; `1` a check or validation failed — for `validate` this includes an invalid
  manifest, which is a validation result; `2` a usage error, an environment problem (engine
  unreachable, git missing, unwritable folder) or an internal error. A `--json` command that cannot
  produce its result prints `{"error": {"kind": "environment" | "internal" | "interrupted",
  "message": ...}}`. Ctrl-C exits `130`.
- Commands that act on a session (`check`, `reset`, `status`, `hint`, `run`, `submit`) use the
  session whose directory contains the current working directory, otherwise the most recently
  started open session *(unconfirmed)*.

## Commands

| Command | Behavior |
| --- | --- |
| `list [--type] [--lang] [--difficulty] [--tag]` | Installed challenges. |
| `show <challenge>` | Metadata, timebox, AI policy; never the solution. |
| `start <challenge> [--ai allowed\|forbidden] [--no-timer] [--snapshots <interval>]` | Consent if untrusted, build the image, create the session and workspace, print the ticket and workspace path. |
| `check` | Run visible and hidden checks; report pass/fail per test. Never touches the user's git state. |
| `reset` | Restore the workspace to its starting state, after confirmation. |
| `status` | Current session: elapsed time vs timebox, last check result. |
| `hint` | Reveal the next hint; logged. |
| `run -- <cmd>` | Run a command in the challenge container on the internal network. |
| `submit [--transcript <file>]` | End the session and write the verified-outcomes report. |
| `sessions` / `report <session>` | Past sessions and their reports. |
| `new <id> --type <type> --lang <lang>` | Scaffold a challenge folder from `templates/`. |
| `validate <path> [--no-write]` | Run `patchground-contract-verification`; CI-friendly. Progress goes to stderr; `--no-write` leaves `verification.json` untouched. |
| `doctor` | Check Docker (or Podman), git, disk; print exact fixes (WSL2 on Windows). |
| `pack add <git-url>[@ref]`, `pack list\|update\|remove` | Manage packs, pinned by commit. |
| `config set <key> <value>` | Defaults: provider, model, editor command. |
| `debrief --ai [--provider] [--yes]` | Experimental AI coaching on a submitted session. |
| `generate ...` | Experimental; exists only once the generator experiment succeeds. |

`cli` contains no business logic: each command parses arguments, calls one module entry point, and
renders its result.
