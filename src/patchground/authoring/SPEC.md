---
id: patchground-authoring
type: module-design
title: "Module: authoring"
status: active
parent: patchground-architecture
depends-on: [patchground-spec, patchground-runner-assets]
implements: [patchground-contract-challenge-format, patchground-contract-cli]
---

# authoring

Owns local creation of authored challenges from packaged template assets. Implements the
`new` command's filesystem behavior, not CLI parsing, validation execution or AI generation.

## Entry point

`create_challenge(id, type_="debug", language="python") -> CreatedChallenge` creates a new
folder named exactly by the validated manifest slug in the current directory. Returns relative
path, ID, template type/language and created relative file names; never returns source contents.

Python/TypeScript × debug/feature are supported; Python/debug remains the default.
Unsupported combinations fail before writing. Existing files,
directories and symlinks, including dangling links, are refused; there is no force option.

## Template and safety boundary

Bundled tiny teaching examples contain a ticket, valid manifest, intentionally incomplete/broken
application, visible/hidden checks, application-only reference patch and pinned container recipe.
They are authoring starting points, not curated realistic exercises. Assets ship in the wheel.
TypeScript environments copy `patchground-runner-assets` verbatim; unavailable or unsafe asset
maps fail before any destination write. Private host file modes remain unchanged; the container
recipe makes installed runner files readable by the unprivileged check user.

Creation reserves the destination exclusively, uses descriptor-relative no-follow file operations
and exclusive file creation, and validates the resulting manifest/layout without executing code.
Writes are confined to newly created entries; no Git state or existing challenge is modified.
On failure or interruption, rollback removes only tracked entries whose identity still matches;
unrelated/replaced entries survive and may leave a partial directory requiring manual inspection.
This is not an atomic filesystem transaction or a sandbox against concurrent same-account tampering.

No container build/run, subprocess, network access, hidden/reference-source output or credential
handling. Depends on `spec` and inert `runner_assets`. CLI owns human/JSON rendering and exit-code mapping.

## Verification

Unit tests cover IDs, unsupported templates, pre-existing and symlink destinations, interruptions,
write failures, and preservation of concurrent additions/replacements. Packaging tests check wheel
assets; Docker integration requires all four unedited generated starters to pass all six validation gates.
