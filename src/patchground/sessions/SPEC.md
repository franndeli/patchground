---
id: patchground-sessions
type: module-design
status: draft
title: "Module: sessions"
parent: patchground-architecture
depends-on: [patchground-spec, patchground-sandbox]
implements: [patchground-contract-execution, patchground-contract-security]
---

# sessions

Owns one attempt at a challenge from `start` to `submit`: the workspace, the session record, the event
log, and the orchestration of checks against the sandbox. It owns Git operations on session
workspaces; the separate verification-copy exception is described in `patchground-architecture`.

## Session layout

```
~/patchground/sessions/<YYYY-MM-DD>-<challenge-id>/
├── workspace/        # the user's repo: challenge workspace/ + visible checks, git init, one initial commit
└── .session/
    ├── session.json  # challenge id + version, source and trust, image digest, ai_policy, start/end, timer on/off
    ├── events.jsonl  # append-only
    ├── original/     # pristine starting workspace + visible checks, read-only
    ├── manifest.json # frozen validated challenge metadata
    ├── hidden/       # private check inputs, never in workspace/
    ├── TICKET.md     # frozen ticket
    └── lock          # advisory lock used by check
```

A second session for the same challenge on the same day gets a numeric suffix. Directory reservation
is atomic; failed creation removes only that attempt's partial directory. The timer is derived from
timestamps; there is no background process.

The local session loop implements start, check, status and reset. Starting validates the authored
local manifest and builds the image; it does not run reference validation. The new baseline repo is
initialized before handoff with a fixed noreply identity, without user/system Git configuration,
hooks or templates. Subsequent check/status operations do not invoke Git in the editable workspace.

Frozen manifest, ticket and hidden checks live under `.session/`, outside `workspace/`; the solution
is never copied. Source edits or removal do not change an existing attempt. Checks use its frozen
command and image ID; a missing image is an environment error, not permission to rebuild or pull.
Session metadata is versioned and paths stay within the session; links must not redirect reads or
writes. Checks are serialized with an advisory lock. Status is read-only and works without Docker.

Copy safety is checked against open descriptors, not a prior pathname scan: editors can replace a
file or directory while a check copies it. Each ancestor and entry is opened without following
links; types and identity are validated on those descriptors. Sensitive-file and Git exclusions
apply before copying. Mutable metadata is additionally required to have one hard link, verified on
the descriptor before any append, so an events file cannot redirect writes into the Git index.
The Git executable is resolved absolutely before changing directories, preventing a relative PATH
entry from selecting a challenge-supplied executable. Raw run logs, even apparently engine-prefixed
lines, never enter events or CLI output.

## Event log

One JSON object per line: `{ts, type, data}`. Types: `session_started`, `check_run` (per-test results,
duration), `reset`, `hint_revealed`, `command_run`, `submitted`, `transcript_attached`,
`debrief_answer`. Events are only appended, never rewritten; readers ignore unknown types.

## Behavior

- **Check:** run a temporary copy of the editable workspace plus frozen hidden checks through
  `sandbox`, then append `check_run` with test ids, statuses and counts, never raw logs. Exclude Git
  metadata and sensitive-file patterns from the copy; reject symlinks, special files and hidden-check
  collisions. Check and status never change the workspace's Git state. Snapshots are not yet built.
- **Snapshots (deferred):** after each check (and periodically with `--snapshots`), write
  `refs/patchground/checks/<n>` using a temporary `GIT_INDEX_FILE`, `git add -A`, `write-tree`,
  `commit-tree`, `update-ref`. This respects `.gitignore`, skips the sensitive-file list from
  `patchground-contract-security`, and never touches HEAD, branches, the index or staging.
- **Reset:** restore ordinary workspace files from `original/`, removing ordinary additions, under
  the same lock as check. Preserve Git metadata and sensitive-pattern entries at every depth,
  including their containing directories; refuse collisions between those entries and starting
  files. Preflight rejects ordinary symlinks and special files before mutation. Protected entries
  are never traversed. Descriptor-relative deletion and exclusive creation avoid following links
  or truncating hardlinked targets. Restored files are owner-writable. Reset never invokes Git,
  changes the timer, or erases history; a successful reset appends one event. The last check remains
  a historical result, not a claim about restored files. Filesystem failure can leave a partial
  restoration, reported explicitly; reset is not transactional and editors should be paused while
  it runs. `original/`, never snapshots, supplies reset and the future regression-test outcome.
- **Hints, run, submit, transcripts:** reveal the next hint, run a command in the container, close the
  session, copy an attached transcript into `.session/` — each logged as an event.
- Hidden checks and the reference solution are never copied into the workspace.

## Boundary

Depends on `spec` and `sandbox`. Exposes read access to session records, events and git data (diffs,
snapshot refs) for `report` and `ai`; they never shell out to git themselves.
