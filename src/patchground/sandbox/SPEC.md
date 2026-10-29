---
id: patchground-sandbox
type: module-design
status: draft
title: "Module: sandbox"
parent: patchground-architecture
depends-on: [patchground-spec]
implements: [patchground-contract-execution]
---

# sandbox

The only module that talks to the container engine (Docker SDK; Podman through its Docker-compatible
socket). It implements both phases of `patchground-contract-execution` and knows nothing about
sessions, packs or reports: callers hand it an environment and files, it hands back results.

## Owns

- **Build:** build a challenge image with network access, cached by a hash of `environment/` plus
  lockfiles; return the image digest. Consent is the caller's job and happens before this is called.
- **Run:** given an image, a set of files to copy in (workspace plus extra paths such as hidden
  checks), a command, services and limits — create the internal network, start services, copy files,
  run, collect `/results`, tear down. Teardown is guaranteed on error, timeout and interrupt.
- **Hardening and limits:** non-root, read-only rootfs, writable `/workspace` and `/results` only,
  dropped capabilities, `no-new-privileges`, CPU/memory/PID/wall-clock limits.
- **JUnit parsing** (`junitparser`) into per-test results. A run result distinguishes passed, failed,
  errored, missing results and limit exceeded.
- **Engine probing** for `doctor`: engine reachable, version, disk available.

## Boundary

Depends only on `spec`. Never executes anything on the host shell, never bind-mounts the user's
workspace writable, never mounts the Docker socket into a container.
