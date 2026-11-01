# Python and TypeScript coverage acceptance

## Scope

Six curated challenges: the existing three Python debugging exercises, Python CSV row-error
collection, TypeScript release-version ordering, and TypeScript event-bus subscriptions. Four
packaged starters cover Python/TypeScript × debug/feature; Python/debug remains the default.
Generated challenge provenance is recorded in each manifest. Difficulty/timeboxes are estimates,
not observed independent-human outcomes. This is implementation/authoring evidence, not a learner trial.

## Observed local checks

- `PATCHGROUND_REQUIRE_DOCKER=1 uv run --quiet pytest -q --tb=short` → 1,104 passed.
  Includes all six challenges, all four unedited starters, actual runner conformance and an immutable
  TypeScript submission with before-failure/after-pass regression evidence and unchanged learner Git.
- `uv run --quiet ruff check .` and `ruff format --check .` → passed (170 Python files).
- `uv run --quiet mypy src` → passed (68 source files).
- Schema equality tests and spec-graph validation → passed; no manifest schema change.
- Clean built wheel in a fresh Python 3.12 environment, outside the source checkout and without AI
  extras → all four starters passed six Docker gates; TypeScript regression verified; learner Git
  bytes unchanged; repeat submission and saved report worked without another engine call; installed
  CLI entry point succeeded. Node and challenge tests never executed on the host.

The runtime pins digest-bound Node 24.15.0, Vitest 5.0.5 and Vite 8.3.5. Actual container conformance
covers identities, assertion failures, skips, runtime transforms, ignored runner configuration,
exact-file selection, empty/invalid/duplicate collection, imports/hooks/unhandled failures,
retries/repeats and an all-pass child exiting nonzero. Runner-wide faults cannot publish passing
JUnit. Runtime success is not TypeScript compiler correctness or protection against malicious forgery.

## Integration failures resolved

- Private-mode scaffold assets remained root-only after Docker COPY. The recipe now explicitly makes
  installed runner resources readable to uid 1000; private host modes were not relaxed.
- Frozen original test files were read-only in regression copies. Disposable copies are writable
  and replaceable while captured/live inputs remain untouched. Unit fixtures now exercise read-only
  inputs, and real TypeScript submit verifies the complete path.
- Deleted TypeScript test modules are removed from original probe copies, never restored into final
  copies. Parser definitions are defensive immutable mappings.
- The CLI Python discovery assertion was updated for the fourth Python challenge, preserving its
  exact-set check. Wheel checks now require every actual canonical asset, without readiness skips.

## Limits and remaining acceptance

The reusable Action smoke now asserts all six committed exercises. Remote CI and actual Action
results must be observed separately; local success does not imply remote success. Independent-human
onboarding/authoring acceptance and ten controlled synthetic learners remain pending. No release,
package publication, deployment or DNS change occurred.
