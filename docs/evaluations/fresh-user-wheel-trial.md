# Fresh-user wheel trials (synthetic)

Two rounds of a "first contact" trial run on 2026-11-01. Each user was a coding agent in an empty
folder that contained only the built wheel. It was told nothing about the product: *"A friend sent
you this file and said 'try this, it's cool'."* Users installed the wheel into a local virtual
environment and used only CLI output and package metadata, with no web search and no reading of
installed sources. They wrote their own `FEEDBACK.md`. These are **synthetic model learners**: they
do not satisfy the independent-human usability gate and are not engineering scores.

## Round 1: wheel from `fb4c52e`

| User | Agent | Furthest point reached |
| --- | --- | --- |
| A | Claude Code (Sonnet) | authored a starter with `new`, then `validate`, `start`, `check`, `hint`, `run`; no submit |
| B | Codex (GPT, low effort) | `new`, then `validate`; did not start a session |

The brief also told them to work only inside their folder. Sessions always went to
`~/patchground/sessions`, so neither user edited a session workspace. That rule shortened round 1
and is a trial-design limitation, not only a product one.

Observed product problems:

- **No challenges in the wheel.** An empty `pgnd list` gave no next step. The README in the package
  metadata assumed a source checkout (`uv tool install .`, `pgnd list examples`) and used relative
  links that do not resolve outside the repository.
- **Contradiction.** The README said pack management was not implemented, while `pgnd pack …` existed.
- **The sessions location could not be configured,** and nothing announced it before `start`.
- **History was always "unavailable"** in agent and editor terminals, with no reason given (see the
  fix below).
- **Smaller issues:** the `pgnd` alias was not explained; "No more authored hints" was printed for a
  challenge with zero hints; the package had no project URLs.

Changes made in response:

- The curated `examples/` now ship in the wheel as a built-in catalog: `pgnd list --builtin`,
  `pgnd start <id>`.
- An empty `list` and `start` print the next commands to run.
- `PATCHGROUND_SESSIONS_DIR` selects the sessions root, and doctor validates it.
- The root help names the alias and the first steps; `hint` reports `total`.
- `project.urls` were added, and the README was rewritten install-first with absolute links.
- **History root cause.** The ignore resolver failed closed on *any* inherited `GIT_*` variable.
  Orca, VS Code and similar terminals export `GIT_ASKPASS` and `GIT_CONFIG_COUNT` with
  `credential.*` keys, which made every capture unavailable. Inert variables, and config injection
  that cannot affect ignore matching, are now tolerated. Everything else still fails closed. The test
  fixture stripped all `GIT_*` variables, which is why the suite never caught this.

## Round 2: wheel with those fixes

The brief was unchanged, except the tool could create files wherever it normally does.

| User | Agent | Outcome |
| --- | --- | --- |
| C | Claude Code (Sonnet) | `pagination-last-page`: regression test, fix, 11/11 checks, submitted; regression verified; about 5 min |
| D | Codex (GPT, low effort) | `pagination-last-page`: regression test first, fix, 11/11 checks, submitted; regression verified; 31 s to submit |

Both users went from `--help` to `doctor` → `list --builtin` → `start` without guessing. Both
praised the ticket, the graduated hints and the before/after regression verification. History was
recorded in both runs.

Both independently reported the same contradiction: the ticket asks for a regression test, but the
report listed the test file as "outside expected paths". Every curated `expected_paths` now
includes `tests/` (challenge versions 1.0.1), and so do the feature starters and the authoring
guidance. Failed checks now point to `pgnd run -- <command>` for visible-test details, and `submit`
ends with next steps.

## Follow-ups fixed after round 2

- Terminal `submit`/`report` output is plain text; the saved `report.md` keeps its escaping.
- `pgnd sessions` names its root and says it lists every attempt there. Commands that cannot select
  a session point to `pgnd sessions`.
- `list --builtin` no longer prints installed-catalog paths in human output.
- The root help says checks run in Docker.

## Still open

- Both round-2 users chose the only beginner challenge. The other five built-ins were not exercised
  from the wheel in this trial; the earlier learner cohort covered them from a prepared session.
- The "blank lines in check output" from round 1 could not be reproduced in a normal terminal.
