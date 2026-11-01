---
id: patchground-runner-assets
type: module-design
status: draft
title: Bundled container runner assets
parent: patchground-architecture
implements: [patchground-contract-execution]
---

## Responsibility

Own canonical, versioned container-only runner assets and locked dependency recipes used by portable
challenge environments and authoring templates. Python exposes asset bytes; it never executes Node,
imports authored code, contacts an engine or runs a challenge. Execution remains solely in sandbox.
Generated environment copies must match these canonical assets rather than diverge.

The approved initial Vitest recipe freezes runtime configuration and reports only factual test
identities/statuses through JUnit, preventing runner-wide errors from producing false passes.
Dependencies install during image build, never check runs. No compiler type-correctness claim.


## Boundary

`vitest_assets()` returns independent byte maps for portable environment copies;
`VITEST_COMMAND` names the fixed container entry point. Wheel resources are the source of truth,
with byte-equality checks preventing example/template drift. The image pins Node by digest and npm
dependencies by lockfile, installing only during build. It explicitly makes copied runner resources
readable to uid 1000 even when authoring inputs have private host modes.

Vitest is chosen for TypeScript transforms and file-qualified identities. Frozen Vitest/Vite
configuration ignores workspace runner configuration, disables watch/retries, and bounds concurrency.
Default discovery selects `.test.ts` except `.git`/`node_modules`; internal `--files` accepts exact
safe relative filenames for regression selection, not arbitrary Vitest arguments.

A parent process owns final JUnit publication after child completion. Actual assertion failures retain
their identities; imports/hooks/unhandled faults, invalid/duplicate identities, empty collection and
unexpected child exit status withhold usable JUnit. No unconditional synthetic failing test is added,
and sandbox exit policy is unchanged. Child logs and intermediate receipts do not enter evidence.
This is a consistency boundary, not protection against malicious local report forgery.

## Verification

Real sandbox conformance covers successful/failed/skipped collection, runtime TypeScript transforms,
identity escaping, configuration isolation, exact-file selection and runner-wide errors, including
all-pass child exit failure. Generated private-mode scaffolds and installed wheel resources are
separate acceptance checks. Runtime transforms make no static type-correctness claim.
