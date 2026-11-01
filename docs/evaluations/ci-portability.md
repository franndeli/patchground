# CI portability follow-up

## Pack staging cleanup — reproduced and repaired

Linux CI on `76d1213` failed the test that preserves a replacement staging directory. Its saved
`(device, inode)` pair could identify a different directory after the original was removed and the
filesystem reused the inode. The fix holds the original directory descriptor through publication,
rollback and cleanup, and passes that identity forward instead of re-statting a changed path.
Cleanup also compares the opened root against its pre-open identity before deleting contents.

The original failing test was reproduced from committed source in a non-root Linux container using
a Docker-managed filesystem volume. A tmpfs-backed run did not reproduce inode recycling. With the
fix, all 97 pack tests passed in the filesystem-backed Linux container. Separate regression tests
cover live-descriptor identity retention and a rename-based swap between stat and open; the latter
also verifies that the moved original remains intact. Existing preservation assertions remain.

## Docker memory reporting — unresolved, better evidence

Earlier CI on `b9dde79` observed exit 137 with no memory-limit classification during a memory-hog
test. The subsequent `76d1213` Docker CI job passed. A supervised worker ran 112 local hardened
memory-hog attempts on Docker 28.5.2/cgroup v2; all confirmed OOM immediately. This does not establish
why the earlier runner differed, and no production retry or exit-code inference was added.

New tests preserve the distinction between engine-confirmed OOM, timeout and ordinary SIGKILL.
The original Docker memory assertion remains strict. Before teardown, failure diagnostics collect
bounded state samples and at most 16 filtered engine events; only state flags, exit code, engine
version and event names/timestamps are exposed. Collection failures use fixed unavailable flags,
never raw exceptions or logs. Tests cover delayed/absent evidence, event-stream closure and failure
paths; late diagnostic evidence cannot rewrite the already classified result.

## Integrated checks

- Full local suite with Docker required: **881 passed**.
- Ruff lint/format and mypy passed.
- Linux pack suite: **97 passed**, after reproducing the baseline cleanup failure.
- The intermittent OOM root cause remains open; a future failure now carries diagnostic evidence.

These are engineering checks, not synthetic learner attempts or independent-human acceptance.

## Root cause of the OOM symptom

A manually triggered stress workflow (`oom-stress.yml`: 10 fresh GitHub runners × 10 repeats of the
memory-limit test) reproduced it in **2 of 100** runs (run 41322438975). The diagnostics showed the
same shape both times: Docker 28.0.4, exit 137, `OOMKilled: false` across eleven state samples over
~1 second, and an event stream containing only `die`, no `oom`. The engine never reported the OOM.
This matches the open upstream containerd issue of lost TaskOOM events (containerd#8893).

Patchground behaved as its contract requires: without engine evidence it did not label exit 137 as
a memory limit. The test, not the product, assumed the engine always reports OOM. The test now runs
the hog up to three times: every attempt must be either labelled `memory` or provably unconfirmed by
the engine (exit 137, no `OOMKilled`, no `oom` event, no label), and at least one attempt must prove
the memory label end to end. A mislabel still fails. The execution contract now states that a lost
engine report surfaces as an unlabelled exit 137. The same stress workflow then passed **100 of 100**
(run 41323311373). Production classification is unchanged.
