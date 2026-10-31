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
- Exit codes: `0` success; `1` a check/validation failed, a diagnostic command failed or exceeded a
  recognized limit, or a listing contains invalid candidates — for `validate` this includes an invalid
  manifest, which is a validation result; `2` a usage error, an environment problem (engine
  unreachable, git missing, unwritable folder) or an internal error. A `--json` command that cannot
  produce its result prints `{"error": {"kind": "environment" | "internal" | "interrupted",
  "message": ...}}`. Ctrl-C exits `130`.
- Commands that act on a session use the session containing the current working directory or an
  explicit `--session <path>`. Outside a session, require selection rather than silently choosing
  the latest attempt.

## Implemented commands

The local practice loop implements `validate`, `start <local-path> [--no-timer] [--no-history]`,
`check [--session <path>]`, `status [--session <path>]` and
`reset [--session <path>] [--yes]`, `doctor`, `list [directory]`, `show <path>` and
`new <id> [--type debug] [--lang python]`, `submit [--session <path>]` and
`report [--session <path>]`, `hint [--session <path>]`, `history [--session <path>]`,
`sessions` and `run [--session <path>] -- <command> [arguments]`,
each with `--json`. Start accepts authored
local paths only; it freezes check inputs and builds, without applying the reference solution.
Status needs no container engine. Checks with no tests or any skipped test do not count as passing.

Local discovery reads immediate challenge folders only; it never builds, runs, installs, resolves
IDs or grants trust. `list` returns matching metadata and all invalid candidates; `show` returns
metadata and ticket. Invalid challenge results exit `1`; invalid command arguments or inaccessible
directories exit `2`. An empty listing succeeds. Doctor probes engine reachability/version, Git and
session-disk availability, exits `0` if healthy and `2` otherwise; it does not measure Docker VM disk.

Authoring `new` creates `<current-directory>/<id>` from packaged runnable Python/debug assets.
The ID follows the manifest slug rules. Type/language default to debug/python; other combinations
exit `2` before writing. Any existing destination, including a dangling symlink, is refused. There
is no overwrite option, Git initialization or automatic container execution. Success exits `0`;
JSON returns `{id, path, type, language, files}` with relative paths, never source contents.
Creation failures exit `2`; safe rollback may leave concurrent additions/replacements intact.

`submit` runs fresh checks against captured input and saves a final report, even for an unsuccessful
solution. It exits `0` for passing checks, `1` for nonpassing checks and `2` for environment/storage
problems. Missing regression evidence does not block finalization. Repeated submission returns the
same frozen result without rerunning. Further check/reset/hint/run operations are rejected on a submitted
session; the workspace remains user-owned and editable. `report` reads a saved report without Docker
and exits `0` even when it describes failed checks; an active session has no final report (exit `2`).
Both select the current session or explicit `--session`, never an implicit latest session.
Transcripts and AI remain deferred. Status exposes active/submitted state and stops the timer at
submission request time.

`hint` reveals the next hint from frozen authored metadata and records its one-based index, not the
hint text. No hints or exhaustion succeeds with an explicit empty result and no new event.
`sessions` lists local attempts newest first without Docker or implicit selection; invalid candidates
are reported and cause exit `1`. An empty listing succeeds; inaccessible storage exits `2`.

`run` requires the `--` boundary. Arguments after it are literal container argv, including flags such
as `--json`; shell syntax requires an explicit container `sh -c`. Patchground options go before it.
Only an editable-workspace copy is supplied, never frozen hidden checks; container edits are discarded.
Output is a sanitized combined tail of at most 64 KiB, always labelled tail-only. JSON returns
`exit_code`, `limit`, `duration_seconds`, `output_tail`, `output_tail_only`; command exit codes remain
data while the CLI exits `0` for success, `1` for nonzero/limited execution, `2` for infrastructure or
usage failure, and `130` for interruption. No JUnit or correctness claim is involved. Arguments and
output are never persisted in session events, and parse failures never echo command arguments.

New sessions capture initial and completed-check checkpoints by default; `--no-history` disables
capture. Existing sessions without history configuration remain unchanged. Capture failure reports
`history.state=unavailable` without invalidating check evidence. `history` reads private checkpoint
metadata without Docker, including after submission; no restore operation is provided. Periodic
background capture is deferred. Checkpoints never modify the learner's Git repository.

The table below also describes planned commands and options; it is not a claim that they all exist.

## Commands

| Command | Behavior |
| --- | --- |
| `list [directory] [--type] [--lang] [--difficulty] [--tag]` | Local challenges immediately inside the directory (default current directory). Installed packs are deferred. |
| `show <path>` | Local metadata, timebox, AI policy and ticket; never the solution. |
| `start <challenge> [--ai allowed\|forbidden] [--no-timer] [--no-history]` | Consent if untrusted, build the image, create the session and workspace, print the ticket and workspace path. |
| `check` | Run visible and hidden checks; report pass/fail per test. Never touches the user's git state. |
| `reset` | Restore ordinary workspace files after confirmation; preserve Git, credential-pattern files, timer and history. `--json` requires `--yes`. |
| `status` | Current session: elapsed time vs timebox, last check result. |
| `hint` | Reveal the next hint; logged. |
| `run -- <cmd>` | Run a command in the challenge container on the internal network. |
| `submit [--session <path>]` | Finalize captured evidence and write verified outcomes; transcript attachment is deferred. |
| `report [--session <path>]` | Read an immutable final report without Docker. |
| `sessions` | List local attempts newest first and report invalid entries, without Docker. |
| `history [--session <path>]` | Read private, privacy-filtered initial/check checkpoint metadata; never restore files. |
| `new <id> [--type debug] [--lang python]` | Create a runnable starter in a new folder from packaged templates; never overwrite or execute. |
| `validate <path> [--no-write]` | Run `patchground-contract-verification`; CI-friendly. Progress goes to stderr; `--no-write` leaves `verification.json` untouched. |
| `doctor` | Check Docker (or Podman), git, disk; print exact fixes (WSL2 on Windows). |
| `pack add <git-url>[@ref]`, `pack list\|update\|remove` | Manage packs, pinned by commit. |
| `config set <key> <value>` | Defaults: provider, model, editor command. |
| `debrief --ai [--provider] [--yes]` | Experimental AI coaching on a submitted session. |
| `generate ...` | Experimental; exists only once the generator experiment succeeds. |

`cli` contains no business logic: each command parses arguments, calls one module entry point, and
renders its result.
