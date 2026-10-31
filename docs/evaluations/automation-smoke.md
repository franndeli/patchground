# Contribution automation verification

The reusable Action is versioned in the main repository, not a separate distribution. Two
supervised implementation workers delivered the core selection/API and packaging/documentation;
coordinator integration used real Git, Docker and an installed core-only package.

## Local evidence

- Full Docker-required suite: **928 passed**; Ruff check/format and mypy passed.
- Real committed inputs preserved dirty checkout files and all Git metadata. Missing execution
  consent refused before builds; unchanged comparison skipped without consent. Broken reference
  validation failed without source, raw logs or private paths in the JSON report.
- The actual install/validation shell bodies from `action.yml` passed from a separate consumer
  checkout with a hostile Python import canary and a deliberately unusable local build backend.
  Installation used the trusted Action project and a private environment; caller Python was not
  imported. Real Docker validation, refusal, unchanged skip and a challenge at the repository root
  passed. Source files and Git metadata stayed byte-identical.
- A clean installed wheel without AI also passed pinned-pack consent, installed validation without
  cache writes, removal followed by check/submit/report, and unchanged learner Git state.

## Integration findings

1. Original checkout executables were excluded during Git retrieval but not later reference
   patching. A fake-Git integration test reproduced the gap; verifier callers now augment mandatory
   input-root exclusions with every original/captured tree. The Docker regression passes.
2. Runtime `python -I` did not protect dependency installation from inherited `PYTHONPATH`.
   A `sitecustomize.py` canary executed before the fix. Installation now clears Python import/startup
   variables and changes to trusted Action source before starting tools; the same smoke passes.
3. Git transport's temporary root name broke manifest/folder identity for single-challenge
   repositories. A bounded disposable copy preserves the original root name, with matching
   selection/skip and installed Docker coverage.

## Limits

Local shell smoke used existing uv/Python, not GitHub's runner or the external setup Action.
`.github/workflows/action-smoke.yml` exercises the actual composite Action against committed examples
and compares checkout Git metadata; its remote result must be observed separately, never inferred
from these local results. No package, release or deployment was published by this evaluation.
These are implementation checks, not independent-human acceptance or synthetic learner trials.
