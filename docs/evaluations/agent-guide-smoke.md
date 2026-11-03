# Synthetic guide and onboarding smoke

## Result

Three synthetic roles completed on 2026-11-03 against published **Patchground 0.1.0**:

- **Learner:** discovered the beginner challenge, reproduced failure, added regression tests, solved,
  checked, submitted, and read the saved report. Final checks: **13 passed**; two new regression cases
  verified. One minor help-text inconsistency was reported.
- **Author:** created a generated-provenance Python/debug challenge, passed all six validation steps,
  then manually solved a fresh session. Final checks: **11 passed**; one new regression case verified.
- **Guide:** returned eight replies covering seven scenario groups, made 24 read-only CLI probes,
  and fetched the actual public skill contents. No critical guidance miss was found in coordinator
  review. The guide independently reported the same help-text inconsistency.

These are observed automated workflows, not human usability, demand, or difficulty evidence.
Independent-human learner and author acceptance is still **pending recruitment**.

The [predeclared protocol](guidance-trial-protocol.md) defines budgets and restrictions.
[Structured evidence](guidance-trial-evidence.json) records supplied-document hashes, requested model
configuration, every CLI command and exit code, exact guide replies, aggregate outcomes, and hashes
of private traces/reports. Raw transcripts, authored private checks, reference patches, and learner
solutions remain outside the repository.

## Artifact and assistant identity

- Source baseline: `01c399afe77706b309223d19bf68ae5aa64b2cef`, plus corrected guidance frozen before
  launch. README and first-session corrections were not yet published during the trials.
- Worker package: separately installed PyPI `patchground==0.1.0`, not the source-built candidate.
  Tools were preinstalled by the coordinator: participant installation was **not tested**.
- Replacement assistant: `codex-cli 0.166.0`, requested `gpt-6-astra`, high reasoning,
  `workspace-write` sandbox with network access enabled. Existing configured authentication only;
  no purchased credits. The launch records establish the requested configuration, not independent
  attestation of the backend model identity.
- Each role used a separate writable directory, virtual environment, session root, and result folder.
  Inherited instructions and the supplied task also constrained behavior. This is neither a
  guide-only causal evaluation nor an adversarial isolation test.
- The publicly fetched skill matched the frozen copy byte-for-byte:
  `1ec0a74d62ab3606f40aa722168a03bc264191a7411efc691f85b3de6d4810c8`.
- Final candidate wheel, tested separately after the help fix:
  `aafe1f193ccc78c80f68426717d867f1014ea1c109058b4cc15ed836078d6417`.
  Its version remains 0.1.0; the hash distinguishes it from the published artifact.

## Learner observations

The learner used the frozen README, first-session guide, skill, and installed help. It selected
`pagination-last-page` 1.0.1 through `list --builtin --difficulty beginner`, then used the printed
workspace. The initial check exited 1 with 7 passed and 3 failed. A focused container diagnostic
reproduced two newly added regression failures before the application edit. Final check and submit
exited 0 with 13 passed, no failures, errors, or skips. Reading the saved report succeeded.

The attempt used 20 of 40 allowed CLI invocations, no hints, and no interactive maintainer help.
All diagnosis, edits, and navigation were performed by the assistant. The submission's approximately
121-second session timer is an automation observation, not a human completion-time estimate.

## Author observations

The author used the public authoring guide and installed help, created `stable-recent-tags` with
`new --type debug --lang python`, and adapted the ticket, application, checks, and reference patch
as a unit. It marked generated provenance. `validate` passed manifest, build, broken failure,
reference success, determinism, and supported anti-gaming checks.

In a fresh session, the initial check exited 1 with 5 passed and 5 failed. Manual workspace edits and
an added regression produced 11 passing checks; submit and report succeeded with verified regression
evidence. The author used 16 of 40 allowed CLI calls. The author knew the intended solution: this is
an authoring/session mechanics check, **not independent challenge-difficulty evidence**. The generated
base-image tag was retained; this does not establish cold-cache reproducibility.

## Guide review

The coordinator read the exact replies and evidence actions rather than accepting worker PASS labels:

- Setup: explained prerequisites and built-in discovery without claiming to install anything.
- Session selection: requested an explicit choice instead of silently choosing the latest attempt.
- Check failures: distinguished exit 1 from infrastructure/usage exit 2 and kept diagnostics in Docker.
- Navigation: did not solve the challenge or reveal a hint after a “do not solve” request.
- Reset/submit: explained destructive/finalization consequences without performing either action.
- Third-party packs: rejected blanket `--yes` advice and required review of the exact version.
- Authoring: identified the supported TypeScript/feature starter and separate authoring directory.
- Missing commands/docs: did not invent `debrief --ai` or configuration commands; described installed
  help as fallback. The public skill fetch succeeded; the unavailable-documents branch was hypothetical.

There were no actual sessions in the guide environment. Multiple attempts, failed checks, and an
untrusted pack were fictional inputs. Unsafe scenarios were **response-only**; no runtime refusal,
consent enforcement, or universal model compliance is established. Installed discovery used the
CLI's default pack root outside the role directory and returned no entries. That is a read-isolation
limitation, not a successful adversarial sandbox test.

## Findings, fixes, and retained failures

1. **Initial launcher failure:** all three Pi workers exited 1 before trial actions because two pstack
   installations registered conflicting tools/flags. These are harness failures, not failed product
   attempts. Global configuration was left unchanged; the replacement managed Codex runs exited 0.
2. **Start help omission:** learner and guide independently observed that the argument description
   omitted built-in IDs despite supporting them. Corrected in `src/patchground/cli/sessions.py`.
   The focused test first failed because the Arguments section lacked `built-in ID`; it passed after
   the text fix. Routing and execution behavior are unchanged. The published package still has the
   old wording until a separately approved release.
3. **320px overflow:** the new browser smoke exposed overflow in the existing illustrated report,
   not the agent card. `web/src/components/Outcomes.astro` now permits grid shrinkage and stacks values
   on narrow screens. The same browser check then passed at 320, 375, and 1440px.
4. **Browser harness unavailable:** shared Chrome DevTools could not open its already-used profile.
   An isolated headless Playwright browser avoided touching the unrelated browser. The earlier
   pending clipboard attempt is not counted as success.
5. **Worker bookkeeping:** one author tool request failed during quoting before shell execution;
   retry succeeded. Guide combined output was truncated; full per-command files were retained and
   missing help was reread. Neither was a product failure.
6. **Coordinator verification:** the first report reread used a symlinked temporary-root spelling
   and correctly received `session paths must not contain symlinks`. Canonical paths succeeded.
   A first validation-summary parser expected `gates` rather than the actual `steps` key; correcting
   the parser and rerunning succeeded. These observation errors are not counted as product defects.

## Independent verification and reproducible checks

The coordinator reread each final report through the installed CLI and compared its parsed JSON with
both the original submit output and the worker's saved report. Both matched; checks passed and
regression evidence was verified, with no changed file outside expected paths. The coordinator also
reran the author's `validate --no-write --json` in Docker: all six steps passed. Review of recorded
read/execute actions found no direct host challenge execution or learner access to private sources;
this is limited trace review, not a sandbox security audit or independent Git-state comparison.

A fresh Python 3.12 environment outside the checkout installed the final candidate wheel, created
all four starters, resolved the built-in ID, showed corrected start argument help, and worked without
Anthropic installed. This smoke did not execute the newly created starter challenges.

Repeatable repository checks:

```sh
uv run pytest tests/unit/test_public_guidance.py tests/unit/cli/test_cli_sessions.py -q
npm --prefix web ci
npm --prefix web run check
npm --prefix web test
npm --prefix web exec -- playwright install chromium
npm --prefix web run test:browser
```

The guidance tests execute the README skill-copy commands and prove repeat installation refuses to
overwrite a customization. Deliberately broken metadata, links, and guidance fixtures fail the checker.
Prior standalone Pi loader evidence established one skill and zero diagnostics; the replacement Codex
trial read the skill file explicitly and does not establish native Codex skill auto-discovery.

Browser smoke uses real clipboard write/readback and keyboard navigation. It also checks simulated
clipboard rejection, unavailable clipboard, no-JavaScript readability, and narrow layouts in both
color preferences. Local verification used installed Chrome via `PLAYWRIGHT_CHANNEL=chrome`; CI is
configured to install Chromium and run the same test, but that new CI run has not yet been observed.
Playwright is a test-only development dependency, not a site/runtime dependency.

Final local checks passed: Ruff lint and formatting (196 files), mypy (69 source files),
1,033 non-Docker tests (103 deselected), schema regeneration with no changes, and 26 site tests.
Browser smoke also passed after the final edits. The full Docker integration suite was not rerun.

No commit, push, package publication, or production deployment is part of this evaluation. The
[human findings record](human-trial-findings.md) remains empty of participant sessions.
