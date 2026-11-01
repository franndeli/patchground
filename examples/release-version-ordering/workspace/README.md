# releasekit

A small pure TypeScript library for ordering strict SemVer release labels. Public exports live in
`src/releasekit/index.ts`; the challenge ticket specifies their contract. Editable checks are merged
into `tests/` when a session starts. Use Patchground's container-backed `check` command to run them;
all runner dependencies are preinstalled in the challenge image. No package install is needed in the
workspace. Application code is original generated challenge material, licensed under Apache-2.0.
