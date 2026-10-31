---
id: patchground-automation
type: module-design
status: active
title: Committed challenge validation automation
parent: patchground-architecture
depends-on: [patchground-packs, patchground-verify, patchground-spec, patchground-safeio]
implements: [patchground-contract-verification, patchground-contract-security]
---

## Responsibility

Select changed challenges from committed input and aggregate the existing verifier's factual
outcomes for a reusable GitHub Action. No second verifier, checkout mutation or publication.
Explicit execution consent precedes builds; unavailable comparison data falls back to all candidates.
No-change is a reported skip, not a claim that unchanged challenges were tested.

## Boundary

`action.yml` is versioned in this repository. Its Linux/Docker composite wrapper installs locked
core-only dependencies from the trusted Action source into a unique private runner-temp environment.
It clears inherited Python import/startup variables and changes to the trusted directory **before**
starting the installer; isolated validation alone does not protect installation. The wrapper resolves
relative source paths from the job workspace and refuses temporary storage inside that source
before creating installation/report files. Runtime uses
`python -I` outside the checkout. Inputs cross the shell boundary through environment variables,
never expression interpolation. Third-party Actions are pinned to full commit SHAs.

The module depends on packs for bounded raw committed Git retrieval, spec for discovery preflight,
safeio for descriptor-safe report creation, and verify for the sole correctness implementation.
It imports no checkout Python, runs no challenge command on the host, and never modifies source
files, HEAD, branches, index, staging or verification records. It creates no session, installation
grant, registry entry, publication or deployment. Network/run restrictions remain the sandbox's.

## API and selection

`validate_changes(source: Path, *, directory=".", base=None, consent=False, sandbox=None)` returns
`AutomationResult`, with `exit_code` and `to_dict()`. Source is a local committed Git repository;
dirty/untracked content is ignored. Directory is a relative in-source path, without traversal,
drive prefixes or controls. Existing packs transport limits and rejection of unsafe Git entries,
symlinks, submodules and LFS apply.

Discover one challenge, a declared pack index, or immediate challenge-bearing child directories.
Preflight every candidate before any build, including unchanged candidates. Empty/invalid discovery
fails; it is not a successful skip. For a challenge at the checkout root, use a bounded disposable
copy with the original root name so manifest/folder identity remains meaningful.

A usable base compares full candidate directory content, executable flags and directories. Added
or changed candidates run; pack metadata changes select all. Report removals without executing them.
Missing, shallow or otherwise unusable comparison data selects all with `fallback_all`; absence of
a requested base uses `all`. A successful comparison uses `changed`. No selected changes succeeds
as `skipped` without requiring execution consent.

Nonempty selection requires explicit consent before any build. The Action's `allow-execution`
input defaults false; only the literal `true` enables it for that invocation. Each candidate calls
`validate_challenge(write=False)`. Original source and every captured input root remain excluded
from host Git executable selection, even when validation runs from a separate trusted directory.

## Reports and failures

Aggregate JSON format `patchground-automation`, version 1, records commit/base, selection mode,
selected/unchanged/removed relative paths, overall status/exit, and per-challenge validity, failed
step, step statuses and run outcomes/counts. It deliberately omits raw verifier details, test IDs,
source, logs, absolute scratch paths and credentials. Unsupported gates retain `not_run`; unchanged
candidates have no fabricated validation result. Manifest diagnostics name a relative file and line.

Core exit codes: 0 validated/skip, 1 failed validation or invalid/empty candidates, 2 usage,
infrastructure or missing consent. Infrastructure failure takes precedence over validation failure.
The entrypoint emits short `patchground-automation-error` records for wrapper failures and 130 for
cancellation; it suppresses raw exception messages and closes reserved descriptors.

The report is exclusively created with a pinned, link-free parent outside the source directory;
never overwrite an existing file. The Action exposes `report-file` before validation. Ordinary
validation failures leave JSON; setup, unsafe-path, cancellation or storage failures may prevent a
usable report. Uploading artifacts is the caller's explicit choice, not an Action side effect.

## Verification

Unit tests cover real committed selection, fallback, consent, preflight, dirty/index preservation,
root challenges, executable-mode changes, safe reports, cancellation and installer isolation.
Docker integration exercises the existing verifier and excludes original-source fake Git binaries.
A dedicated CI workflow invokes the actual Action against committed examples, validates its JSON
and compares checkout Git metadata. Clean-install smoke also tests malicious caller Python imports,
consent refusal, real Docker validation, unchanged skip and an unchanged checkout.
