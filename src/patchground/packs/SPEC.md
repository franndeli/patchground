---
id: patchground-packs
type: module-design
status: draft
title: "Module: packs"
parent: patchground-architecture
depends-on: [patchground-spec]
implements: [patchground-contract-security]
---

# packs

Answers "which challenge folder is this, and how far do we trust it?", and manages installed packs.

## Owns

- **Resolution:** a challenge reference is either an id (looked up across installed packs; ambiguity
  is an error naming the candidates) or a local path. The result carries the folder, its pack (name,
  version, commit) and its trust level from `patchground-contract-security`.
- **Install, update, remove:** clone a pack's git URL, pin it to a commit SHA, validate `pack.yaml`,
  and store it read-only under `~/.patchground/packs/<pack>@<sha>/`. `update` produces the change
  summary that the consent prompt shows.
- **Consent records:** which untrusted pack versions the user accepted, stored under `~/.patchground/`.
  Deciding *whether* to prompt is here; prompting is `cli`'s job.
- **Index** for `list`: challenge metadata across packs, filterable by type, language, difficulty
  and tag.

Only `patchground-core` from the official org counts as official; trust is never inferred from a pack's
own `pack.yaml`.

## Boundary

Depends on `spec`; uses git only through clone and fetch for pack sources and never touches session
workspaces. Never builds or runs anything.
