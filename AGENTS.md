# Patchground

Open-source, local-first CLI (`patchground`, alias `pgnd`) for practicing real software
engineering. Users solve challenges in their own editor with their own AI; Patchground
runs verification in Docker and reports verified outcomes.

## Where the rules live

- Product: `goal-and-requirements.md`. System and module boundaries: `architecture.md`.
- Contracts you implement against: `docs/contracts/*.md`.
- Each module's responsibility and boundary: `src/patchground/<module>/SPEC.md`.
- Background and roadmap: `docs/spec.md` (not authoritative).

Read the SPEC of the module you are changing and the contracts it implements. If a spec and the
code disagree, or a spec is ambiguous, stop and ask. A change that alters a boundary or contract
updates the owning spec in the same change.

## Current programme: local-first public product

The owner approved expanding beyond M1 toward the roadmap and a public documentation/catalog site
at patchground.dev. Delivery boundaries and resume context live in `docs/launch-brief.md` and
`docs/delivery-plan.md`; the shared TODO list tracks active work. Four Python/TypeScript debugging/feature starters, six curated challenges
and immutable verified-outcomes reports are implemented, together with hints, disposable diagnostic
commands, session browsing, private checkpoint history and consent-gated pinned packs. Consent-gated contribution automation and bounded TypeScript runner evidence are implemented.
Remaining slices cover the public site and bounded optional AI experiments. Each subsystem still requires an
accepted design and owning-spec updates.

Use existing configured model subscriptions/local models only; do not buy credits or paid services.
Git pushes are authorized, but DNS changes, production deployments, package publication and release
creation require explicit approval at publication. Synthetic model learners do not satisfy the
independent human usability gate. Record their configuration and observed outcomes honestly.

Do NOT build hosted challenge execution, accounts, overall scoring or proctoring. Stages remain
reserved until their contract is explicitly redesigned. Preserve the hardened Docker boundary,
user Git state, optional-AI separation and all privacy/publication guards below.

## Hard rules

- Challenge commands run only in containers via `sandbox/`. Never through the host shell.
- Build phase may use the network; run phase uses an internal network only.
- Third-party packs: ask for consent before building or running anything from them.
- Never copy `solution/` or hidden checks into the workspace; never print hidden tests.
- At runtime, never modify an existing challenge workspace's git HEAD, branches, index or staging
  area. Initializing a fresh session repo before handoff is allowed. This does not prohibit normal
  development commits in the Patchground source repository when requested by the owner.
- Never write API keys to disk or logs.
- Correctness comes from tests only. No overall scores.
- Core must work without the `[ai]` extra installed.
- Use the glossary terms exactly: challenge, pack, session, workspace, check, debrief.

## Secrets and personal data (absolute — this repo is public)

- Never commit, push, print, log, or paste into issues, PRs, comments or commit messages: API keys,
  tokens, passwords, private keys, `.env` contents, cookies, credentials of any kind.
- Never include personal data: email addresses (other than GitHub noreply addresses), phone numbers,
  home paths such as `/Users/<name>/`, machine names, or private repo URLs.
- Never bypass the guards: no `--no-verify`, no `git add -f` on ignored files, no editing or
  disabling `.githooks/`, `.gitignore`, `.github/workflows/secret-scan.yml` or GitHub push protection.
- Never change `user.email` away from the GitHub noreply address, never force-push, never create
  releases, gists or new public repos without the owner's explicit request.
- Tests and examples use obviously fake values (`sk-test-not-a-real-key`), never real ones.
- If a hook or scan blocks you, stop and tell the owner. Do not work around it. If a secret may have
  been exposed, say so immediately: it must be rotated, not just deleted.

One-time setup per clone: `brew install gitleaks && git config core.hooksPath .githooks`.

## Conventions

Python 3.12+, uv, Typer, Rich, Pydantic v2, ruff, mypy (strict on spec/, verify/, report/).
Every command supports `--json`. Manifest errors name the file and line.
Unit tests per module; Docker integration tests marked `@pytest.mark.docker`.
Work in small PR-sized steps; run lint, types and tests before calling a step done.

## Definition of done for M0

`uv run pgnd validate examples/<challenge>` passes on a valid example and fails, naming the step,
on a broken one; the exported schema in `schema/` is up to date; CI is green.
