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
- Commands that act on a session use the session containing the current working directory or an
  explicit `--session <path>`. Outside a session, require selection rather than silently choosing
  the latest attempt.

## Implemented commands

The first playable slice implements `validate`, `start <local-path> [--no-timer]`,
`check [--session <path>]`, `status [--session <path>]` and
`reset [--session <path>] [--yes]`, `doctor`, `list [directory]` and `show <path>`,
each with `--json`. Start accepts authored
local paths only; it freezes check inputs and builds, without applying the reference solution.
Status needs no container engine. Checks with no tests or any skipped test do not count as passing.

Local discovery reads immediate challenge folders only; it never builds, runs, installs, resolves
IDs or grants trust. `list` returns matching metadata and all invalid candidates; `show` returns
metadata and ticket. Invalid challenge results exit `1`; invalid command arguments or inaccessible
directories exit `2`. An empty listing succeeds. Doctor probes engine reachability/version, Git and
session-disk availability, exits `0` if healthy and `2` otherwise; it does not measure Docker VM disk.

The table below also describes planned commands and options; it is not a claim that they all exist.

## Commands

| Command | Behavior |
| --- | --- |
| `list [directory] [--type] [--lang] [--difficulty] [--tag]` | Local challenges immediately inside the directory (default current directory). Installed packs are deferred. |
| `show <path>` | Local metadata, timebox, AI policy and ticket; never the solution. |
| `start <challenge> [--ai allowed\|forbidden] [--no-timer] [--snapshots <interval>]` | Consent if untrusted, build the image, create the session and workspace, print the ticket and workspace path. |
| `check` | Run visible and hidden checks; report pass/fail per test. Never touches the user's git state. |
| `reset` | Restore ordinary workspace files after confirmation; preserve Git, credential-pattern files, timer and history. `--json` requires `--yes`. |
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
