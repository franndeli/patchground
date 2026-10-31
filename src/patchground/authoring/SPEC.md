---
id: patchground-authoring
type: module-design
title: "Module: authoring"
status: active
parent: patchground-architecture
depends-on: [patchground-spec]
implements: [patchground-contract-challenge-format, patchground-contract-cli]
---

# authoring

Owns local creation of authored challenges from packaged template assets. Implements the
`new` command's filesystem behavior, not CLI parsing, validation execution or AI generation.

## Entry point

`create_challenge(id, type_="debug", language="python") -> CreatedChallenge` creates a new
folder named exactly by the validated manifest slug in the current directory. Returns relative
path, ID, template type/language and created relative file names; never returns source contents.

Only Python/debug is implemented. Unsupported combinations fail before writing. Existing files,
directories and symlinks, including dangling links, are refused; there is no force option.

## Template and safety boundary

The bundled tiny teaching example contains a ticket, valid manifest, intentionally broken
application, conventional visible/hidden pytest checks, application-only reference patch and
Dockerfile with a pinned pytest version. It is a starting point for authors, not a fourth curated
realistic exercise. Assets ship in the wheel and do not depend on the source checkout.

Creation reserves the destination exclusively, uses descriptor-relative no-follow file operations
and exclusive file creation, and validates the resulting manifest/layout without executing code.
Writes are confined to newly created entries; no Git state or existing challenge is modified.
On failure or interruption, rollback removes only tracked entries whose identity still matches;
unrelated/replaced entries survive and may leave a partial directory requiring manual inspection.
This is not an atomic filesystem transaction or a sandbox against concurrent same-account tampering.

No container build/run, subprocess, network access, hidden/reference-source output or credential
handling. Depends only on `spec`. CLI owns human/JSON rendering and exit-code mapping.

## Verification

Unit tests cover IDs, unsupported templates, pre-existing and symlink destinations, interruptions,
write failures, and preservation of concurrent additions/replacements. Packaging tests check wheel
assets; Docker integration requires the unedited generated starter to pass all six validation gates.
