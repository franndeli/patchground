# Installing and using challenge packs

A pack is a Git repository containing `pack.yaml` and its indexed challenge folders.
Patchground imports committed files, pins their commit and content, and does not execute anything
during installation. All installed packs are labelled **unofficial**: a familiar name is not proof
of origin.

```sh
pgnd pack add /absolute/path/to/a/local/pack --ref HEAD
pgnd pack list
pgnd list --installed
pgnd show sample-pack:challenge-id
pgnd start sample-pack:challenge-id
```

Public credential-free HTTPS Git URLs are also supported. Private authentication and SSH are not.
Do not put credentials in a URL. Local sources must be ordinary Git repositories with safe,
non-symlinked paths; use their canonical physical path on systems with temporary-directory aliases.
Uncommitted local edits are not imported.

Plain `pgnd list` still discovers local folders. Installed IDs must be unique, or use
`pack-name:challenge-id`. Existing local folders and explicit `./folder` or absolute paths retain
local behavior. Passing an installed cache path does not bypass consent.

## Review before execution

Before the first installed build, Patchground shows the exact source, commit and content identity,
plus every indexed challenge's complete Dockerfile, services and test command. Approving covers that
version, not future updates. Oversized reviews fail rather than truncate; hidden checks and reference
solutions are not shown. A changed identity invalidates an interactive confirmation.

Building an untrusted Dockerfile is sensitive. Opening its workspace in an editor can also run
tooling **outside Docker**; use a containerized development environment for untrusted sources.
Import itself rejects symbolic links, submodules and Git LFS pointers, isolates Git configuration,
and never runs source hooks or filters. Export is limited to 100 MiB/10,000 files, with a five-minute
transport deadline; transferred Git history can be larger.

Every command supports `--json`. JSON never prompts: start, validate or changed update returns
`consent_required` and a complete review if approval is needed. Use `--yes` only when you explicitly
intend to approve the selected version:

```sh
pgnd validate sample-pack:challenge-id --yes --json
pgnd start sample-pack:challenge-id --yes --json
```

Installed validation checks a disposable verified copy. It does not modify the immutable cache or
trust an imported `verification.json`.

## Updates and removal

```sh
pgnd pack update sample-pack
pgnd pack update sample-pack --ref another-branch
pgnd pack remove sample-pack
```

Updates follow the originally selected ref unless changed. Review lists added, removed and changed
challenges and complete recipes before activation. Declining preserves the previous active revision;
older cached versions remain available. Add never silently replaces an installed pack from another
source or switches it to a new commit.

Removal confirms before clearing cached revisions and future-start consent. Existing sessions keep
their frozen inputs, image and accepted provenance, so their checks and reports remain independent
of the pack. A missing image is still an environment error, not permission to silently rebuild.

Missing/tampered cache content is reported, never trusted or silently repaired by listing. Unknown
cache directories are not swept. If publication durability or removal cleanup fails, inspect
`pgnd pack list --json`: an error may follow a committed state change and does not promise rollback.
