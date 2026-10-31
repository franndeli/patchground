# Your first local session

Patchground is a local engineering-practice CLI. No account, API key, or built-in AI is needed.
You work in your own editor; Patchground runs challenge checks in Docker.

## Install and discover

Install Python 3.12+, uv, Git and Docker (Docker Desktop on macOS; Docker Engine on Linux).
Start Docker. On Windows use WSL2 with Docker Desktop, and run these commands inside WSL2.
From a checkout of this repository:

```sh
uv tool install .
pgnd doctor
pgnd list examples --lang python
pgnd show examples/pagination-last-page
pgnd start examples/pagination-last-page
```

The first image build needs network access. Later checks use the frozen local image and an
internal-only network. Start builds but does not verify the reference solution; challenge authors
use `pgnd validate <path>` separately.

Only start challenges you authored or reviewed. Listing or showing a challenge is not an endorsement.
Patchground does not run challenge commands on your host, but your editor or agent can execute
project tooling when you open a workspace. Remote pack installation and consent workflows are not
part of this prototype.

## Solve in your editor

Open the **workspace path printed by start**, not the source challenge folder. Read the ticket
printed by start (or use `show` before starting). From a terminal inside that workspace:

```sh
pgnd status
pgnd check
```

The initial check should fail: that is the exercise. Explore the code and visible tests, reproduce
the reported behavior, write a regression test, and fix the cause. Run `pgnd check` again. Only tests
that actually run and all pass produce exit code `0`; failing or skipped checks produce `1`.
Invalid input or infrastructure problems produce `2`.

The runner never prints raw test output or hidden test sources. Test IDs and outcomes tell you what
passed or failed. Hidden checks live outside your editable workspace; this is a local honor system,
not an anti-cheating platform.

A passing check finishes the current practice loop. There is no `submit`, score, report, or automatic
regression-test assessment yet. Keep your own notes on the cause, fix and evidence.

## Retry safely

```sh
pgnd reset
pgnd check
```

Reset asks before discarding edits. It restores starting files and removes ordinary additions while
preserving Git metadata and credential-pattern entries, even in nested folders. The timer and event
history remain; the last check shown by status is historical until you check again. A reset does not
unstage your changes: the Git index stays exactly as it was.

Pause editor/agent writes first. Reset rejects symlinks/special files in ordinary workspace content
and refuses conflicts with protected files. It is not an atomic transaction: a disk or permission
failure may leave a partially restored workspace. Resolve that problem and retry, or start a fresh
session. There is no backup or undo; make your own backup before confirming if you need one.

For automation, all commands support `--json`; reset additionally requires `--yes`. Outside a
workspace, use `--session <session-path>` with check, status or reset. There is no automatic
latest-session selection. Start a new session to get a fresh timer.

## Troubleshooting

- **Docker unavailable:** run `pgnd doctor` and follow its platform-specific fix. Status, discovery
  and reset do not require Docker. Doctor measures session-disk space, not Docker VM free space.
- **Frozen image missing:** restore the exact local image if available, or start a new session.
  Check never silently rebuilds or pulls it.
- **Session busy:** wait for its check/reset to finish; only one mutation runs at a time.
- **No session selected:** change into the printed workspace or pass `--session` explicitly.
- **No challenges listed:** point `list` at the parent directory of challenge folders. It scans
  immediate children only, not recursively. `show` and `start` accept challenge paths, not IDs.
- **Unsupported services:** use a single-container challenge with `environment.services: []`.
- **Invalid challenge:** diagnostics identify files and lines without echoing arbitrary manifest
  values. Authors should fix the manifest/layout and run `pgnd validate` before sharing it.

## Fresh-user acceptance checklist

Automated tests cannot establish that the exercise is useful. The remaining M1 acceptance gate is
one person unfamiliar with the project completing this loop without maintainer assistance:

- Install from this checkout and interpret doctor output.
- Find the example and understand the ticket without seeing its solution.
- Start a session, observe failing checks, fix the code and reach passing checks in their own editor.
- Understand status, reset the workspace and observe failing checks again.
- Explain any confusing messages, missing instructions, or unrealistic parts of the exercise.

Record blockers and usability observations without credentials, machine identifiers or personal
paths. The later external-validation milestone expands this to more learners and an independent
challenge author; it is not completed by the automated suite.
