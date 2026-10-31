---
id: patchground-safeio
type: module-design
status: active
title: Shared safe local filesystem and Git selection
parent: patchground-architecture
---

## Responsibility

Shared non-domain primitives for descriptor-pinned filesystem access and safe Git executable
selection. They reject symlinked ancestors, special files and changed inode identities; opening
nonblocking prevents FIFO races from hanging. Callers choose their domain exception and label.
Sessions retains compatibility wrappers; packs uses the same primitives rather than depending on
session lifecycle code or duplicating safety logic.

Git selection considers only absolute PATH entries outside lexical/resolved caller input trees and
cwd, including resolved executable symlink targets. Candidates are inspected, never executed to
identify them. Absolute external installations are trusted, not authenticated. Missing safe Git
raises an error; callers decide whether their optional operation becomes unavailable.

## Boundary

Standard library only. Does not execute Git, interpret manifests/configuration, manage consent,
copy domain trees, run containers or own session/pack state. Mutation policy and transactionality
remain with the calling module.
