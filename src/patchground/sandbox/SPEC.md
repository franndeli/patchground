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
- **Engine probing** for `doctor`: engine reachable, engine kind (Docker/Podman) and version.

## Implementation notes (M0)

- The API takes plain values (paths, strings, `Limits`); for M0 it imports no other patchground
  module. Services are not built yet.
- `probe_engine(timeout=5)` returns an `EngineProbe`; it never raises for an unusable engine. It
  pings and reads the version with a per-request HTTP timeout and always closes the client. Failures
  are reported only as an `EngineProblem` category (`not_running`, `permission`, `timeout`,
  `misconfigured`, `unhealthy`) derived from the exception chain, never as raw engine text (which
  may carry socket paths or hosts). It never builds, pulls or runs anything. Engine-side disk usage
  is not probed; `doctor` checks host disk for sessions through `sessions`.
- Builds use the Engine API's classic builder (what the Docker SDK drives), tagged
  `patchground/<name>:<hash12>` over the context directory; build containers are memory-capped.
  A build has a wall-clock budget (`timeout_seconds`, default 1800 s), checked whenever the builder
  emits output and enforced for silent steps by an equal HTTP read timeout (so a build that goes
  quiet just before the deadline may overrun it by up to one more budget). Exceeding it raises
  `BuildFailed`; closing the build connection makes the engine cancel the build and remove its
  intermediate container. Engine 4xx answers are `BuildFailed` (the challenge's fault); 5xx, no
  status, or a connection lost before the deadline are `SandboxError` (the environment's fault).
- A run's wall clock is `container.wait(timeout=…)`; a read timeout or connection error from it
  counts as the limit only once the deadline (minus 1 s) has passed, otherwise it is a lost engine
  (`SandboxError`, teardown still runs). Unreadable layer files are `SandboxError`, never `OSError`.
- Files reach the run container through two fresh labelled volumes (`/workspace`, `/results`). The
  engine refuses archives into a read-only rootfs and ignores a tar's root (`.`) entry, so a
  never-started "seed" container mounting the same volumes takes the archive at `/`; this is what
  makes both volume roots owned by uid 1000. The seed container never runs anything.
- The run outcome comes from `/results/junit.xml` only: limit exceeded (timeout or OOM) first, then
  missing/unparsable results, then errored > failed > passed; zero test cases is errored.
- `RunResult.log_tail` is raw test-runner output and may contain test sources (assertion rewrites,
  tracebacks), including those of hidden checks. Callers must not display it for runs that
  included hidden layers. Prefixes such as `[patchground]` are not a trust boundary: tests can
  print them too. Diagnostics exposed to users must come from structured outcomes, not parsed logs.

## Boundary

Depends only on `spec`. Never executes anything on the host shell, never bind-mounts the user's
workspace writable, never mounts the Docker socket into a container.
