# Test fixtures: broken challenges

Each folder is a complete challenge, a copy of `examples/pagination-last-page`, broken in
exactly one way so that `pgnd validate` fails at a known step. Folder name == `id`. Do not "fix"
them; tests assert on the failing step and, for the manifest fixture, on the reported lines.

| Fixture | Fails at | Why |
| --- | --- | --- |
| `invalid-manifest/` | step 0, manifest valid | Several schema errors in `challenge.yaml` (see below). |
| `services-unsupported/` | step 0, manifest valid | `environment.services: ["postgres:16"]`; services must be `[]` in M0. Otherwise identical to the example. |
| `build-fails/` | step 1, builds | Dockerfile is `FROM busybox:1.36` then `RUN exit 1`. |
| `broken-state-passes/` | step 2, broken state fails | Hidden tests only cover exact-multiple page counts, which the bug doesn't affect, so every hidden test passes on the starting workspace. |
| `reference-fails/` | step 3, reference passes | `reference.patch` applies cleanly (`git apply -p1`) but swaps `//` for `round()`, which rounds 2.5 down to 2: `test_partial_last_page_is_reachable`, `test_total_pages_rounds_up` and `test_second_to_last_page_has_next` still fail. |

## `invalid-manifest/challenge.yaml` errors

All must be reported in one pass, each naming `challenge.yaml` and the line:

| Line | Path | Problem |
| --- | --- | --- |
| 5 | `type` | `bugfix` is not one of `debug`, `feature`, `review`, `refactor`. |
| 12 | `estimated_minutes` | Unknown top-level key. |
| 17 | `environment.network` | Unknown key inside `environment`. |
| — | `timebox_minutes` | Required field missing. It has no line of its own; expect the error to point at the top-level mapping (line 1). |

Line 24 is an `x-notes` key: extension keys are accepted and must **not** be reported.

## Not collected by the repo's pytest

`conftest.py` in this folder sets `collect_ignore_glob` so the repo's own `pytest` run does not
collect the challenge tests inside these fixtures.
