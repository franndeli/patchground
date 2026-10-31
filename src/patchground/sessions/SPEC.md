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
    ├── submission/   # atomically committed private final/, report.json, report.md, receipt.json
    └── lock          # advisory lock shared by check, reset and submit
```

A second session for the same challenge on the same day gets a numeric suffix. Directory reservation
is atomic; failed creation removes only that attempt's partial directory. The timer is derived from
timestamps; there is no background process.

The local session loop implements start, check, status, reset and frozen submission/readback. Starting validates the authored
local manifest and builds the image; it does not run reference validation. The new baseline repo is
initialized before handoff with a fixed noreply identity, without user/system Git configuration,
hooks or templates. Subsequent check/status operations do not invoke Git in the editable workspace.

Frozen manifest, ticket and hidden checks live under `.session/`, outside `workspace/`; the solution
is never copied. Source edits or removal do not change an existing attempt. Checks use its frozen
command and image ID; a missing image is an environment error, not permission to rebuild or pull.
Session metadata is versioned and paths stay within the session; links must not redirect reads or
writes. Checks, reset and submission are serialized with an advisory lock. Status is read-only and works without Docker.

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
  collisions. Check and status never change the workspace's Git state. Submitted sessions reject checks under the shared lock. Snapshots are not yet built.
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
  it runs. `original/`, never snapshots, supplies reset and the regression-test outcome.
- **Submit:** immutable closure and readback use the lifecycle API below; report owns analysis.
- **Hints, run, transcripts (deferred):** reveal the next hint, run a command in the container, or
  attach a transcript with explicit consent — each logged as an event.
- Hidden checks and the reference solution are never copied into the workspace.

## Boundary

Depends on `spec` and `sandbox`. Exposes read access to session records, events and git data (diffs,
snapshot refs) for `report` and `ai`; they never shell out to git themselves.

## Submission lifecycle and public API

Sessions owns safe snapshots, the shared lock, closure/receipt persistence and read access.
Report owns factual analysis, sandbox regression probes, structured reports and Markdown rendering;
sessions never imports report. CLI orchestration remains outside sessions.

- `SubmissionSnapshot` exposes `session`, `original`, `final`, `hidden` Paths; `record` SessionRecord;
  `manifest`; `events` tuple of Event; aware `requested_at`; and `saved_report` dict or None.
- `prepare_submission(session=None, *, root=None)` is a context manager holding the shared lock
  throughout analysis, fresh verification and commit. It captures original, final and hidden inputs
  in private locations using descriptor-validated copies. Final includes ordinary Git-ignored files,
  excludes Git and credential patterns, and never changes the live workspace or Git bytes. A completed
  submission yields its saved report without recopying live inputs or running an engine.
- `check_submission(snapshot, *, sandbox=engine)` runs the combined captured final and hidden inputs,
  reusing sanitized CheckResult handling without recording a practice `check_run` event.
- `commit_submission(snapshot, report, markdown, final_check)` runs within the preparation context.
  It writes a complete private staging bundle containing final workspace, JSON report, Markdown and
  a versioned typed session receipt with content/permission integrity inventory, request timestamp
  and final check.
  Files and directories are synced before an atomic rename publishes `submission/`; that rename is
  the closure point. A failure afterwards cannot reopen the session or claim rollback. Repeated commit
  preserves the existing bundle. Failed staging remains private and is ignored, never cleaned through
  a potentially replaced pathname.
- `read_submission(session=None, *, root=None)` validates the receipt, bundle layout and complete
  artifact inventory, rejecting unsafe paths, corrupt artifacts and hardlinked files. It returns saved
  JSON without Docker, execution, rebuilding or writes; an active session raises SessionError.

Schema-1 session records remain unchanged and active until a committed bundle exists. SessionStatus
adds `state` (active/submitted) and `submitted_at`; submitted elapsed time stops at the request time,
and last_check is the receipt's frozen final result. Failed checks may close a session; infrastructure
failures before publication leave it active. Reset rejects closure under the same shared lock.

The bundle is authoritative even if syncing its parent directory or appending the submitted audit
fails. Post-publication errors explicitly state that the bundle may already be published and direct
the caller to retry submit; they never imply rollback or an active session. Completed report, status
and repeated-submit reads validate the bundle and session metadata without opening the now-irrelevant
live workspace, original or hidden trees, even if those trees have been removed or replaced by unsafe
entries. Active-session tree validation stays strict.

Receipt schema 1 stores the exact serialized submitted event plus the byte length and SHA-256 of the
complete journal before publication. Read-only access verifies those preceding bytes and accepts only
an exact prefix of the expected submission append as an interrupted write. A subsequent
prepare_submission reconciles by appending the proven missing suffix under the lock, never truncating
or rewriting any bytes. Unrelated malformed tails, altered history and inconsistent complete events
are rejected without repair. Complete later events remain unchanged, including unknown event types.
Receipt version 1 requires the complete audit proof; unsupported receipt versions and missing or
malformed proof fields are rejected. Schema-1 active session records and their strict validation
remain unchanged. No practice check or submission mutates user Git metadata.
