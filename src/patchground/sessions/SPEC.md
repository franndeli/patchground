---
id: patchground-sessions
type: module-design
status: draft
title: "Module: sessions"
parent: patchground-architecture
depends-on: [patchground-spec, patchground-sandbox, patchground-packs, patchground-safeio]
implements: [patchground-contract-execution, patchground-contract-security]
---

# sessions

Owns one attempt at a challenge from `start` to `submit`: the workspace, the session record, the event
log, and the orchestration of checks against the sandbox. It initializes fresh workspace Git before handoff and owns private session Git checkpoint history;
existing learner repositories are never used for Git writes or execution. The separate verification-copy
exception is described in `patchground-architecture`.

## Session layout

The sessions root is `~/patchground/sessions/`, or `PATCHGROUND_SESSIONS_DIR` when set. The override
must be absolute (relative values are rejected so every working directory selects the same root) and
is canonicalized once; links below it are still refused. Doctor reports an invalid override.

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
    ├── history.git/  # optional private checkpoint objects/internal refs
    └── lock          # advisory lock shared by mutating practice/submission operations
```

A second session for the same challenge on the same day gets a numeric suffix. Directory reservation
is atomic; failed creation removes only that attempt's partial directory. The timer is derived from
timestamps; there is no background process.

The session loop implements start, check, status, reset and frozen submission/readback. Starting
uses packs-owned preparation to resolve inputs and enforce installed-version consent before build;
it validates the captured manifest but does not run reference validation. Pack identity and unofficial
trust are frozen in new records/results; legacy local records without pack metadata remain valid.
Checks and reports need neither installed cache nor registry after start. The new baseline repo is
initialized before handoff with a fixed noreply identity, without user/system Git configuration,
hooks or templates. Subsequent Git subprocesses run only in private temporary directories. Checkpoints use isolated
temporary bare repositories and publish validated loose objects/internal refs into private
`history.git/`; Git never loads the stored private repository configuration.

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
All session Git operations share an executable resolver: only absolute PATH entries outside the
current directory and all known learner, authored-source and captured-input trees are eligible.
Both candidate locations and resolved symlink targets are checked against lexical and canonical
input roots, then the candidate must be a regular executable file. Relative/empty PATH entries are
never searched, and candidates are never executed to establish identity. The selected absolute
executable is bound once for exclusion discovery and reused through checkpoint plumbing, even if
PATH changes during a check. Standard absolute installation paths and installation symlinks outside
excluded trees remain supported; their provenance is trusted as part of the caller's host installation,
not authenticated by Patchground. If no safe candidate can be established, initial Git initialization
fails safely and optional history is unavailable. Excluding a recorded authored-source path does not
require that source to still exist; checks continue using frozen session inputs after source removal.
Raw check logs, even apparently engine-prefixed lines, never enter events or CLI output.
Diagnostic command tails are an explicit separate display surface; neither their arguments nor
output enter the journal.

## Event log

One JSON object per line: `{ts, type, data}`. Types: `session_started`, `check_run` (per-test results,
duration), `reset`, `hint_revealed`, `command_run`, `submitted`, `transcript_attached`,
`debrief_answer`, `history_recorded` (initial checkpoint status). Events are only appended, never rewritten; readers ignore unknown types.

## Behavior

- **Check:** run a temporary copy of the editable workspace plus frozen hidden checks through
  `sandbox`, then append `check_run` with test ids, statuses and counts, never raw logs. Exclude Git
  metadata and sensitive-file patterns from the copy; reject symlinks, special files and hidden-check
  collisions. Check and status never change the workspace's Git state. Submitted sessions reject
  checks under the shared lock. The editable copy is retained separately before merging hidden checks;
  completed checks checkpoint that captured editable input, never the hidden-merged run copy or the
  later live workspace. Capture failures preserve the complete check result, passed/counts semantics
  and normal `check_run` evidence, returning `history.state=unavailable` with a fixed safe explanation.
- **History:** `start_session(..., history=True)` explicitly enables checkpoint capture for new
  sessions; opt-out records `history_enabled=False`. Schema-1 records missing that field remain
  disabled and are never auto-migrated. `StartedSession.history` and `CheckResult.history` are optional
  `SnapshotStatus` values (default None for legacy results), with state recorded/unavailable/disabled,
  optional ref and fixed safe detail. The exact returned check result is persisted in `check_run`.
  Initial capture uses pristine editable originals and a separate `history_recorded` event, preserving
  the established `session_started` shape. There is no periodic capture or restore-from-history API.
  Captures exclude Git metadata and credential patterns through descriptor-safe copies. Native Git
  ignore matching runs against captured root/nested `.gitignore` files in fresh trusted metadata,
  honoring copied repository `info/exclude`, effective `core.excludesFile`, default XDG Git ignore
  and `core.ignoreCase`. Exclusion inputs are resolved before the check runs, separately from the
  exact captured editable input. Config precedence is system, XDG global, home global, local;
  explicit absolute `GIT_CONFIG_SYSTEM`/`GIT_CONFIG_GLOBAL` and disabling system config are honored.
  Variables editors, agent terminals and credential helpers export routinely (`GIT_ASKPASS`,
  `GIT_TERMINAL_PROMPT`, editor/pager/SSH and author/committer identity variables) cannot change
  discovery or ignore matching and are tolerated. Well-formed `GIT_CONFIG_COUNT`/`KEY_n`/`VALUE_n`
  injection is tolerated only when no injected key is `core.excludesFile`, `core.ignoreCase`,
  `core.worktree`, `include.*`, `includeIf.*` or `extensions.*`; malformed injection fails closed.
  Git discovers its compiled system-config path via a read-only data query; unsupported discovery
  makes capture unavailable. Configuration is parsed as data via stdin, never copied to disk;
  only exclusion-rule bytes and sanitized fixed private config are written. No raw configuration,
  command arguments or errors enter events or output.
  Resolution fails closed for include/includeIf (including apparently inapplicable conditions),
  extensions, linked worktrees/gitfiles, missing original Git context, relative exclusion/config
  paths, other inherited GIT_* overrides, unreadable/redirected/shared/special or oversized exclusion
  inputs, and unrecognized override values. These cases report unavailable; they never fall back
  to `.gitignore`-only snapshots. Ordinary standalone Git metadata is required even when the actual
  captured input is a temporary check copy. Missing ordinary config/ignore files are empty where
  Git permits them; local repository config and HEAD must exist. Descriptor-safe reads reject
  redirected ancestors and bound files to 1 MiB. Filtered history is not a complete replay image of
  ignored files included in checks.
  Git uses a fixed absolute executable, allowlisted environment, disabled hooks/config/pager/network
  protocols and raw hash-object/index plumbing; no clean/smudge filters or challenge commands run on
  the host. Its temporary index and writable repository live in system temporary storage, never the
  learner repository. Private publication validates existing paths, hardlink counts, fixed config and
  object hashes; writes only exclusive new files, shares identical objects, syncs objects before refs,
  and never overwrites an existing ref. Partial writes and orphan refs remain private and unadvertised;
  retries allocate new refs and preserve existing bytes. No automatic destructive cleanup occurs.
  `history_for_session(session=None, *, root=None) -> HistoryResult` is read-only and works after
  submission without a workspace or Docker. It returns session, enabled, availability
  (available/disabled/unavailable), and a tuple of HistoryEntry values: ref, commit, kind
  (initial/check), aware ts, optional check_outcome. Only refs linked to recorded session evidence
  with valid commit/tree/blob objects are listed; unsafe/corrupt or missing checkpoint data yields
  unavailable rather than fabricated history. Reads never invoke Git or repair/create storage.
  Compatibility is forward-reading: current code reads prior schema-1 sessions and receipts unchanged;
  older strict readers may reject newly created records/results containing history fields. Opt-out
  preserves ordinary practice behavior; rollback never rewrites existing session metadata or Git.
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
- **Hints:** under the shared lock, reject closed sessions and reveal the next frozen authored
  hint. Record one one-based index per reveal, not the hint text. Empty/exhausted hints succeed
  without another event; inconsistent indices fail rather than skip or repeat evidence.
- **Diagnostic commands:** under the shared lock, reject closure, safely copy editable inputs
  without hidden checks, and call sandbox's literal-argv command API using the frozen image.
  Discard container edits. Return the bounded sanitized output tail but persist timing, exit/limit
  or fixed interruption/environment-error metadata only, never arguments/output. No correctness
  claim or practice-check count is inferred from these commands.
- **Session browsing:** read immediate local attempts, sort newest first by recorded start time,
  and report unsafe/invalid candidates without exposing private parse errors. No Docker, implicit
  selection, repairs or writes. Ordinary unrelated folders are ignored.
- **Transcripts (deferred):** attachment would require explicit consent.
- Hidden checks and the reference solution are never copied into the workspace.

## Boundary

Depends on `spec`, `sandbox`, packs preparation and shared `safeio`. Exposes read access to session records, events and git data (diffs,
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
