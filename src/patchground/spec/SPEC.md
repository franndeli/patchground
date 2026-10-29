---
id: patchground-spec
type: module-design
status: draft
title: "Module: spec"
parent: patchground-architecture
implements: [patchground-contract-challenge-format]
---

# spec

Turns challenge and pack folders into typed, validated objects. It is the executable form of
`patchground-contract-challenge-format`: if the contract and the models disagree, the contract wins
and the models are fixed.

## Owns

- Pydantic v2 models for `challenge.yaml` and `pack.yaml` v0.1, including enums for type, difficulty,
  AI policy and provenance, the `x-` extension rule, and path checks that every referenced path exists
  and stays inside the folder.
- Loading: YAML parsed with source positions so every error names the file and line, and reports all
  problems in one pass instead of stopping at the first.
- JSON Schema export to `schema/`, versioned by `spec_version`. The exported schema is generated, never
  hand-edited; CI fails if it is stale.

## Boundary

A leaf: no imports from other Patchground modules, no Docker, no git, no network, no filesystem writes
other than schema export. mypy strict.
