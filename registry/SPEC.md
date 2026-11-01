---
id: patchground-registry
type: module-design
status: active
title: "Module: registry"
parent: patchground-architecture
depends-on: [patchground-spec, patchground-verify]
implements: [patchground-contract-security, patchground-contract-verification]
---

# registry

The public index of community challenge packs. It answers one question for the website and,
later, for `pgnd pack add <name>`: *which packs exist, and which of them has Patchground itself
verified?* It is a decentralised model in the style of package galleries: content stays in the
author's repository; Patchground owns only the index and the gate.

## Publish-and-appear

There is no submission form, pull request or human review. An author validates locally, puts
challenge folders beside a `pack.yaml` in a public repository, and tags it with the GitHub topic
`patchground-pack` (or adds its `https://` clone URL to `registry/sources.yaml` for other hosts).
A scheduled workflow discovers tagged repositories, re-validates every challenge with the real
validator, and publishes the result. Passing packs appear in the catalog with a *verified* badge;
everything else appears on the public status page with the failing step. The CLI commands
`pgnd pack publish` (validate + tag in one step) and name resolution in `pack add` are planned and
documented as such; the registry contract does not depend on them.

## The gate

A pack is listed only if, at a specific commit, in Patchground's own CI:

1. the clone is within limits (100 MiB, 10 000 regular files, no symlinks) — the same bounds as
   installed packs — and a secret scan finds nothing;
2. `pack.yaml` and every listed `challenge.yaml` load through `patchground-spec`, every listed
   folder exists, ids match folders, `content_license` and `provenance` are declared, and
   `environment.services` is empty;
3. `pgnd validate` passes for every challenge — the full `patchground-contract-verification` gate,
   because a local `verification.json` is not portable proof.

Validation is the only judge; the badge therefore means exactly "passed the validator here", never
"realistic" or "reviewed". Official/curated status remains reserved (`patchground-contract-security`).

## Outputs and their boundary

`index.json` holds verified packs: name, source, commit, verified_at, version, description, host
stats (stars, forks, pushed_at) and, per challenge, the same public allowlist the website uses
(id, title, summary, type, languages, tags, difficulty, timebox, provenance) plus a ticket URL at
the verified commit. `status.json` holds every source seen with result (`verified`, `failed`,
`error`, `skipped`), failing step and challenge, and a detail scrubbed of runner paths. Neither
file ever contains hidden checks, hints, solutions, raw logs or source code. Both are written only
by CI.

Pack names are first-seen-wins; a later pack with a taken name is reported as a policy failure.
A validation failure drops a pack from the index; an infrastructure error (clone, timeout, engine)
keeps its last verified entry and is reported as `error`. Unchanged commits are skipped for 30
days, then re-verified; at most 20 fresh validations run per invocation so cost stays bounded. A single-source run
(`--source`) updates only that source and keeps every other entry. Files are rewritten only when
their content changes, so a run that finds nothing new does not commit a new timestamp.

## Security posture

The crawler runs untrusted Dockerfiles. It therefore runs in a dedicated job with a read-only token
and no secrets, on an ephemeral runner, with per-pack clone and validation timeouts and an isolated
git environment (no configured helpers, hooks or filters; `https` only outside tests). A separate
job with write access commits the two JSON files and the regenerated site catalog. The checkout keeps no
credentials, and the read-only token (used only for discovery) is stripped from the environment of
every tool that touches a pack. The gitleaks binary is checksum-pinned, and in CI a pack that could
not be scanned is never listed. The crawler is
the consenting party for third-party content under `patchground-contract-security`; its approval
covers one commit of one pack and never extends to users, who still receive the consent prompt when
installing.

## Boundary

`registry/crawl.py` is a standalone script outside the `patchground` package: standard library plus
`patchground.spec` loaders and the `pgnd validate --json` CLI. It never imports sandbox or sessions
and never runs challenge code on the host. The website consumes `index.json` and `status.json`
(`patchground-web`); the packs module will consume `index.json` for name resolution.
