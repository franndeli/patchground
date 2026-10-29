---
id: patchground-contract-execution
type: architecture-design
status: draft
title: "Contract: execution"
parent: patchground-architecture
depends-on: [patchground-contract-challenge-format, patchground-contract-security]
---

# Execution

Every challenge runs in two separate phases. Keeping them apart is what lets dependencies install with
the network while checks run without it.

| Phase | When | Network | What runs |
| --- | --- | --- | --- |
| Build | On `start` and `validate`, cached by a hash of `environment/` plus lockfiles | External network allowed | `docker build` of the challenge Dockerfile. For untrusted sources, only after consent (`patchground-contract-security`). |
| Run | Every `check`, `run` and validation step | A per-run Docker network with `internal: true`: test container and services reach each other, nothing reaches the internet | `test_command` (or the user's `run` command) against a copy of the workspace |

## Rules

- `test_command` uses preinstalled dependencies only. A challenge whose tests need a download is
  invalid.
- Challenge commands run only inside containers, never through the host shell.
- The workspace is **copied** into a fresh container, never bind-mounted writable. Hidden checks are
  added to the copy, never to the user's workspace.
- `PG_RESULTS=/results`; results are read from `/results/junit.xml`. A missing or unparsable file is
  an error result, not a pass.
- Services named in `environment.services` start on the same internal network, reachable by service
  name.
- Every run tears down its containers and network, also on failure, timeout or interrupt.

## Container defaults

- Build: no host mounts, no Docker socket, build-time limits.
- Run: non-root user; read-only root filesystem with only `/workspace` and `/results` writable;
  dropped Linux capabilities and `no-new-privileges`.
- Limits per check: 2 CPUs, 2 GB memory, 512 PIDs, 10 minutes wall clock. Exceeding one is reported as
  such, distinct from failing tests.

## A check, step by step

1. Copy the workspace into a fresh container from the built image; add the hidden checks.
2. Create the internal network; start services on it.
3. Run `test_command` with `PG_RESULTS=/results`.
4. Parse `/results/junit.xml` into per-test results.
5. Record a `check_run` event (owned by `patchground-sessions`) and tear everything down.
6. Snapshot the workspace into `refs/patchground/checks/<n>` (see `patchground-sessions`).
