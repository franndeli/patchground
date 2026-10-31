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

## Local discovery (M1)

Before packs exist, `list [directory]` and `show <path>` work on local folders only, through
`discover_challenges(directory, filters)` and `show_challenge(path)`:

- `list` examines the immediate children of `directory` (default: the current directory), sorted by
  name; never deeper. A child is a candidate when it holds a `challenge.yaml` entry. Each candidate is
  validated with `spec.load_challenge`; valid ones are summarised (id, path, title, version, type,
  summary, languages, tags, difficulty, timebox, AI policy) and filtered by `type`, `lang`,
  `difficulty` and `tag` (all given must match; text compares ignore case). Invalid candidates are
  always reported with file/line diagnostics, regardless of filters, never silently hidden.
  Manifest diagnostics omit arbitrary input values, which could contain private data.
- Symlinked children are reported as invalid and never followed; `challenge.yaml` and `TICKET.md`
  must be regular files, and the ticket is opened nonblocking without following a symlink and
  capped at 256 KiB. Nonblocking access avoids hanging if an editor replaces it with a FIFO.
- `show` returns the summary plus author, license, provenance, hint count, services and the ticket.
  Output never includes the solution, hidden checks, hint text or the test command.
- A missing or non-directory argument raises `DiscoveryError` (environment). Discovery never
  builds, runs, installs, records paths, resolves ids, or assigns trust.

Only `patchground-core` from the official org counts as official; trust is never inferred from a pack's
own `pack.yaml`.

## Boundary

Depends on `spec`; uses git only through clone and fetch for pack sources and never touches session
workspaces. Never builds or runs anything.
