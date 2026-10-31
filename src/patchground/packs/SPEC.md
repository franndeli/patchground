---
id: patchground-packs
type: module-design
status: active
title: "Module: packs"
parent: patchground-architecture
depends-on: [patchground-spec, patchground-safeio]
implements: [patchground-contract-security, patchground-contract-cli]
---

# packs

Owns source resolution, immutable installed content and exact-version execution consent. It never
builds or runs a challenge and never touches session workspaces. CLI owns prompts; sessions and
verify must use preparation before executing installed inputs. Shared filesystem/Git selection
belongs to `patchground-safeio`, not sessions.

## Resolution and discovery

Plain `list [directory]` remains immediate-folder local discovery. It validates candidate manifests,
applies all filters, reports invalid candidates regardless of filters and never initializes state.
Local `show` reads metadata and a bounded regular ticket, never hidden checks, solutions or hints.
Existing local folders and explicit paths retain local behavior; unique bare IDs select active
installed challenges, while ambiguity names qualified `pack-name:challenge-id` alternatives.

Managed-cache paths never become authored paths, including aliases, missing versions and corrupt
state. Installed listings verify cached content and expose qualified references and pinned identity;
invalid content is reported, not repaired. Installed show uses a disposable verified copy without
execution consent and reports canonical cache paths. Listing integrity costs a full bounded read.

## Import and immutable state

Public credential-free HTTPS and local committed Git repositories are supported. SSH, private
authentication, submodules, symlinks and LFS pointers are unsupported. Dirty local files are ignored.
Git uses isolated metadata, configuration and environment, with no configured helpers, hooks,
filters, templates, redirects or alternative protocols. Local object data is copied, never
transported through source repository configuration. Raw blobs preserve committed bytes rather than
attribute-transformed archives; object hashes are checked before asserting commit provenance.
Transport has a five-minute deadline; timeout/interruption terminates Git and its helpers together.
Git transfer/object copying may exceed the exported limit of 100 MiB and 10,000 regular files.

Every indexed challenge is structurally validated before publication. Cache identity binds source,
commit and captured content, including executable flags and directory paths. Copies reject unsafe
entries and racing replacements through descriptor checks. Stored verification records are never
proof of safety. All installed packs are unofficial under `patchground-contract-security`.

Cache versions are read-only under `~/.patchground/packs/<name>@<commit>/`; the private
`registry.json` stores active revisions, metadata and consent. Mutations share a lock and publish
metadata atomically. Catalog writes cannot exceed their 8 MiB read limit. Cache files are synced
before publication; a failure after catalog replacement reports uncertain durability and never
deletes newly referenced content or claims rollback. Earlier versions remain available.

Add is idempotent only for matching source/commit/content; it does not silently update or switch
sources. Existing destinations are never replaced: identical content can recover interrupted
publication, differing content fails closed. Stage cleanup is identity-bound; no name/age-based
orphan sweeping deletes unrelated data. Removal unregisters all versions and consent, then removes
their caches; a cleanup failure explicitly reports partial removal. Sessions and sources remain
untouched.

## Consent and execution input

`prepare_execution(reference, yes=False, expected_identity=None)` captures installed bytes into
private temporary storage, verifies identity and yields that exact input alongside its canonical
source path. Cache and original local-source roots accompany it for safe Git exclusion. Authored
local inputs pass through unchanged. Session provenance stays frozen after cache removal.

A missing grant raises `ConsentRequired` with every indexed challenge's Dockerfile, services and
command before any build. Complete recipes are bounded to 64 KiB per Dockerfile/command and 1 MiB
aggregate; oversized previews fail rather than truncate. Approval binds the whole immutable version,
not future updates. Interactive retries require the expected identity; changes fail closed.
Updates review added/removed/changed challenges and complete recipes before changing the active
version. No approval leaves the previous active revision unchanged. Core enforcement, not CLI
prompting alone, prevents cache-path consent bypasses.
