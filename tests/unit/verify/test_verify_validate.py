"""Unit tests for validate_challenge with a fake sandbox (no Docker); git apply uses host git."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from patchground.sandbox import (
    BuildFailed,
    BuildResult,
    EngineUnavailable,
    Limits,
    RunOutcome,
    RunResult,
    SandboxError,
    TestResult,
    TestStatus,
)
from patchground.spec import loader as loader_module
from patchground.verify import (
    VERIFICATION_FILE,
    StepName,
    StepStatus,
    ValidationReport,
    VerifyEnvironmentError,
    read_verification,
    validate_challenge,
)
from patchground.verify import record as record_module
from patchground.verify import reference as reference_module
from patchground.verify import validate as validate_module

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "pagination-last-page"
FIXTURES = REPO / "tests" / "fixtures"

P, F, E, S = TestStatus.PASSED, TestStatus.FAILED, TestStatus.ERRORED, TestStatus.SKIPPED
VISIBLE = [f"tests.test_pagination::test_v{i}" for i in range(3)]
HIDDEN = [f"tests.test_pagination_hidden::test_h{i}" for i in range(2)]
STALE_RECORD = '{"format": "patchground-verification", "format_version": 1}\n'


def result(
    tests: Sequence[tuple[str, TestStatus]],
    outcome: RunOutcome | None = None,
    *,
    limit: str | None = None,
    log_tail: str = "",
) -> RunResult:
    parsed = tuple(
        TestResult(id=i, name=i.split("::")[-1], classname=i.split("::")[0], status=s)
        for i, s in tests
    )
    if outcome is None:
        statuses = {t.status for t in parsed}
        outcome = (
            RunOutcome.ERRORED
            if E in statuses or not parsed
            else RunOutcome.FAILED
            if F in statuses
            else RunOutcome.PASSED
        )
    return RunResult(outcome, parsed, 0, limit, log_tail)


def statuses(ids: Sequence[str], status: TestStatus) -> list[tuple[str, TestStatus]]:
    return [(i, status) for i in ids]


Responder = Callable[[str, Sequence[Path]], RunResult]


@dataclass
class FakeSandbox:
    """Answers run_check by run kind: 'visible', 'hidden' (starting state) or 'reference'."""

    root: Path
    runs: dict[str, RunResult] = field(default_factory=dict)
    build_error: Exception | None = None
    run_error: Exception | None = None
    calls: list[tuple[str, list[Path]]] = field(default_factory=list)
    reference_snapshots: list[dict[str, str]] = field(default_factory=list)

    def build_image(self, dockerfile: Path, *, name: str) -> BuildResult:
        self.calls.append(("build", [dockerfile]))
        if self.build_error is not None:
            raise self.build_error
        return BuildResult(image_id="sha256:fake", tag=f"patchground/{name}:000000000000", log="")

    def run_check(
        self, image_id: str, layers: Sequence[Path], command: str, *, limits: Limits
    ) -> RunResult:
        assert image_id == "sha256:fake"
        kind = self.kind(layers)
        self.calls.append((kind, list(layers)))
        if kind == "reference":
            self.reference_snapshots.append(reference_module.snapshot(layers[0]))
        if self.run_error is not None:
            raise self.run_error
        if kind.startswith("anti-"):
            raw = self.runs["hidden"]
            editable = {test.id for test in self.runs["visible"].tests}
            if kind == "anti-deleted":
                return replace(raw, tests=tuple(t for t in raw.tests if t.id not in editable))
            if kind == "anti-skipped":
                return replace(
                    raw,
                    tests=tuple(replace(t, status=S) if t.id in editable else t for t in raw.tests),
                )
            return raw
        return self.runs[kind]

    def kind(self, layers: Sequence[Path]) -> str:
        if layers[0].parent.name in ("anti-empty", "anti-deleted", "anti-skipped"):
            return layers[0].parent.name
        if layers[0] != self.root / "workspace":
            return "reference"
        return "hidden" if layers[-1] == self.root / "checks" / "hidden" else "visible"


def good_runs() -> dict[str, RunResult]:
    return {
        "visible": result(statuses(VISIBLE, P)),
        "hidden": result([*statuses(VISIBLE, P), (HIDDEN[0], F), (HIDDEN[1], P)]),
        "reference": result(statuses(VISIBLE + HIDDEN, P)),
    }


@pytest.fixture
def challenge(tmp_path: Path) -> Path:
    target = tmp_path / "pagination-last-page"
    shutil.copytree(EXAMPLE, target)
    (target / VERIFICATION_FILE).unlink(missing_ok=True)
    return target


@pytest.fixture
def box(challenge: Path) -> FakeSandbox:
    return FakeSandbox(root=challenge.resolve(), runs=good_runs())


def validate(challenge: Path, box: FakeSandbox, *, write: bool = True) -> ValidationReport:
    return validate_challenge(challenge, sandbox=box, write=write)


def assert_failed_at(report: ValidationReport, name: StepName, *, detail: str = "") -> None:
    assert not report.valid
    assert report.failed_step is name
    step = report.step(name)
    assert step.status is StepStatus.FAILED
    assert detail in step.detail
    names = [s.name for s in report.steps]
    for later in names[names.index(name) + 1 :]:
        assert report.step(later).status is StepStatus.NOT_RUN
    assert report.verification_file is None
    assert not (report.folder / VERIFICATION_FILE).exists()


# --------------------------------------------------------------------------------------------------
# Success and verification.json
# --------------------------------------------------------------------------------------------------


def test_valid_challenge_writes_verification_json(challenge: Path, box: FakeSandbox) -> None:
    report = validate(challenge, box)

    assert report.valid
    assert report.failed_step is None
    assert [s.status for s in report.steps] == [StepStatus.PASSED] * 6
    assert "3 runs" in report.step(StepName.DETERMINISM).detail
    assert [kind for kind, _ in box.calls] == (
        ["build"]
        + ["visible", "hidden", "reference"] * 3
        + ["anti-empty", "anti-deleted", "anti-skipped"]
    )
    assert len(report.step(StepName.ANTI_GAMING).runs) == 3
    assert report.verification_file == challenge.resolve() / VERIFICATION_FILE

    text = (challenge / VERIFICATION_FILE).read_text()
    assert text.endswith("}\n")
    assert text.startswith('{\n  "format"')
    doc = json.loads(text)
    assert set(doc) == {
        "format",
        "format_version",
        "patchground_version",
        "challenge",
        "image_id",
        "validated_at",
        "steps",
    }
    assert doc["format"] == "patchground-verification"
    assert doc["format_version"] == 1
    assert doc["challenge"] == {
        "id": "pagination-last-page",
        "version": "1.0.0",
        "spec_version": "0.1",
    }
    assert doc["image_id"] == "sha256:fake"
    assert doc["validated_at"].endswith("Z")
    assert [s["name"] for s in doc["steps"]] == [
        "manifest",
        "build",
        "broken_fails",
        "reference_passes",
        "determinism",
        "anti_gaming",
    ]
    for step in doc["steps"]:
        assert set(step) == {"name", "status", "detail", "started_at", "finished_at", "runs"}
    broken = doc["steps"][2]
    assert [r["label"] for r in broken["runs"]] == ["workspace+visible", "workspace+visible+hidden"]
    assert broken["runs"][1]["counts"] == {"passed": 4, "failed": 1, "errored": 0, "skipped": 0}
    assert broken["runs"][1]["tests"][-1] == {"id": HIDDEN[1], "status": "passed"}
    assert doc["steps"][3]["runs"][0]["label"] == "reference+visible+hidden"
    assert doc["steps"][4]["status"] == "passed"
    assert doc["steps"][4]["started_at"] is not None
    assert len(doc["steps"][4]["runs"]) == 9

    # Nothing from the patch or hidden sources ends up in the record.
    assert "math.ceil" not in text
    assert "def test_" not in text
    assert read_verification(challenge) == doc
    # Atomic write leaves no temp file behind.
    assert sorted(p.name for p in challenge.iterdir() if p.name.startswith(".")) == []


def test_layers_and_reference_copy(challenge: Path, box: FakeSandbox) -> None:
    validate(challenge, box, write=False)
    root = challenge.resolve()
    by_kind = {kind: layers for kind, layers in box.calls}
    assert by_kind["visible"] == [root / "workspace", root / "checks/visible"]
    assert by_kind["hidden"] == [
        root / "workspace",
        root / "checks/visible",
        root / "checks/hidden",
    ]
    copy, *checks = by_kind["reference"]
    assert checks == [root / "checks/visible", root / "checks/hidden"]
    assert not copy.is_relative_to(root)
    assert not copy.exists()  # temp copy removed afterwards
    # The patch was applied to the copy, never to the challenge's workspace.
    assert "math.ceil" not in (root / "workspace/src/catalog/pagination.py").read_text()
    assert box.reference_snapshots[0] != reference_module.snapshot(root / "workspace")


def test_write_false_writes_nothing(challenge: Path, box: FakeSandbox) -> None:
    report = validate(challenge, box, write=False)
    assert report.valid
    assert report.verification_file is None
    assert not (challenge / VERIFICATION_FILE).exists()


def test_report_to_dict(challenge: Path, box: FakeSandbox) -> None:
    data = validate(challenge, box).to_dict()
    assert data["valid"] is True
    assert data["failed_step"] is None
    assert data["verification_file"].endswith(VERIFICATION_FILE)
    assert len(data["steps"]) == 6
    json.dumps(data)


def test_reference_failure_removes_stale_verification(challenge: Path, box: FakeSandbox) -> None:
    (challenge / VERIFICATION_FILE).write_text(STALE_RECORD)
    box.runs["reference"] = result([(VISIBLE[0], F)])
    report = validate(challenge, box)
    assert report.failed_step is StepName.REFERENCE_PASSES
    assert not (challenge / VERIFICATION_FILE).exists()


# --------------------------------------------------------------------------------------------------
# Step 0: manifest
# --------------------------------------------------------------------------------------------------


def test_manifest_issues_are_reported_with_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    box = FakeSandbox(root=FIXTURES / "invalid-manifest")
    report = validate_challenge(Path("tests/fixtures/invalid-manifest"), sandbox=box)
    assert_failed_at(report, StepName.MANIFEST, detail="4 problems")
    step = report.step(StepName.MANIFEST)
    assert "tests/fixtures/invalid-manifest/challenge.yaml:5: type: " in step.issue_lines[1]
    assert [issue.line for issue in step.issues] == [1, 5, 12, 17]
    assert step.to_dict()["issues"][1]["line"] == 5
    assert box.calls == []


def test_missing_folder_fails_manifest(tmp_path: Path, box: FakeSandbox) -> None:
    report = validate_challenge(tmp_path / "nope", sandbox=box)
    assert_failed_at(report, StepName.MANIFEST, detail="1 problem in")
    assert box.calls == []


def test_services_are_not_supported(challenge: Path, box: FakeSandbox) -> None:
    manifest = challenge / "challenge.yaml"
    manifest.write_text(manifest.read_text().replace("services: []", 'services: ["postgres:16"]'))
    report = validate(challenge, box)
    assert_failed_at(
        report,
        StepName.MANIFEST,
        detail="environment.services is not supported yet (deferred beyond the local prototype)",
    )
    (issue,) = report.step(StepName.MANIFEST).issues
    assert (issue.line, issue.field) == (16, "environment.services")
    assert box.calls == []


# --------------------------------------------------------------------------------------------------
# Step 1: build
# --------------------------------------------------------------------------------------------------


def test_build_failure_keeps_last_30_log_lines(challenge: Path, box: FakeSandbox) -> None:
    box.build_error = BuildFailed("".join(f"line {i}\n" for i in range(100)))
    report = validate(challenge, box)
    assert_failed_at(report, StepName.BUILD, detail="image build failed")
    tail = report.step(StepName.BUILD).log_tail
    assert tail is not None
    assert tail.splitlines() == [f"line {i}" for i in range(70, 100)]
    assert report.step(StepName.BUILD).to_dict()["log_tail"] == tail


@pytest.mark.parametrize(
    "error", [EngineUnavailable("no socket"), SandboxError("engine exploded")], ids=repr
)
def test_engine_problems_at_build_are_environment_errors(
    challenge: Path, box: FakeSandbox, error: Exception
) -> None:
    box.build_error = error
    with pytest.raises(VerifyEnvironmentError):
        validate(challenge, box)
    assert not (challenge / VERIFICATION_FILE).exists()


@pytest.mark.parametrize(
    "error", [EngineUnavailable("gone"), SandboxError("container vanished")], ids=repr
)
def test_engine_problems_at_run_are_environment_errors(
    challenge: Path, box: FakeSandbox, error: Exception
) -> None:
    box.run_error = error
    with pytest.raises(VerifyEnvironmentError):
        validate(challenge, box)


# --------------------------------------------------------------------------------------------------
# Step 2: broken state fails
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["visible", "hidden"])
@pytest.mark.parametrize(
    ("outcome", "limit", "words"),
    [
        (RunOutcome.MISSING_RESULTS, None, "missing results"),
        (RunOutcome.LIMIT_EXCEEDED, "timeout", "timeout limit"),
    ],
)
def test_inconclusive_starting_runs_fail(
    challenge: Path,
    box: FakeSandbox,
    kind: str,
    outcome: RunOutcome,
    limit: str | None,
    words: str,
) -> None:
    box.runs[kind] = result(
        [],
        outcome,
        limit=limit,
        log_tail="secret hidden source\n[patchground] secret spoofed note\n",
    )
    report = validate(challenge, box)
    assert_failed_at(report, StepName.BROKEN_FAILS, detail="inconclusive")
    step = report.step(StepName.BROKEN_FAILS)
    assert words in step.detail
    assert step.notes == ()
    assert "secret" not in json.dumps(step.to_dict())


def test_no_hidden_tests_fails(challenge: Path, box: FakeSandbox) -> None:
    box.runs["hidden"] = result(statuses(VISIBLE, P))
    report = validate(challenge, box)
    assert_failed_at(report, StepName.BROKEN_FAILS, detail="no hidden tests detected")


def test_every_hidden_test_passing_fails(challenge: Path, box: FakeSandbox) -> None:
    box.runs["hidden"] = result(statuses(VISIBLE + HIDDEN, P))
    report = validate(challenge, box)
    assert_failed_at(report, StepName.BROKEN_FAILS, detail="passes every hidden check")


def test_hidden_skipped_does_not_count_as_failing(challenge: Path, box: FakeSandbox) -> None:
    box.runs["hidden"] = result(statuses(VISIBLE, P) + statuses(HIDDEN, S))
    report = validate(challenge, box)
    assert_failed_at(report, StepName.BROKEN_FAILS, detail="passes every hidden check")


def test_hidden_error_counts_and_visible_failures_are_allowed(
    challenge: Path, box: FakeSandbox
) -> None:
    box.runs["visible"] = result(statuses(VISIBLE, F))
    box.runs["hidden"] = result([*statuses(VISIBLE, F), (HIDDEN[0], E), (HIDDEN[1], P)])
    report = validate(challenge, box, write=False)
    assert report.valid
    detail = report.step(StepName.BROKEN_FAILS).detail
    assert "1 of 2 hidden tests fail" in detail
    assert "3 failed" in detail


def test_no_visible_checks(challenge: Path, box: FakeSandbox) -> None:
    manifest = challenge / "challenge.yaml"
    manifest.write_text(manifest.read_text().replace("  visible: checks/visible\n", ""))
    shutil.rmtree(challenge / "checks" / "visible")
    box.runs = {
        "visible": result([]),  # workspace alone: no tests at all
        "hidden": result([(HIDDEN[0], F), (HIDDEN[1], P)]),
        "reference": result(statuses(HIDDEN, P)),
    }
    report = validate(challenge, box, write=False)
    assert report.valid
    labels = [r.label for r in report.step(StepName.BROKEN_FAILS).runs]
    assert labels == ["workspace", "workspace+hidden"]
    assert report.step(StepName.REFERENCE_PASSES).runs[0].label == "reference+hidden"


def test_visible_test_vanishing_with_hidden_checks_fails(challenge: Path, box: FakeSandbox) -> None:
    # Hidden checks (e.g. a conftest.py) deselect or rename a visible test.
    box.runs["hidden"] = result([*statuses(VISIBLE[1:], P), (HIDDEN[0], F), (HIDDEN[1], P)])
    report = validate(challenge, box)
    assert_failed_at(
        report,
        StepName.BROKEN_FAILS,
        detail="inconclusive: hidden checks changed or deselected visible tests: " + VISIBLE[0],
    )
    assert len(report.step(StepName.BROKEN_FAILS).runs) == 2


# --------------------------------------------------------------------------------------------------
# Step 3: reference passes
# --------------------------------------------------------------------------------------------------


def test_reference_skipped_test_counts_as_not_passing(challenge: Path, box: FakeSandbox) -> None:
    box.runs["reference"] = result([*statuses(VISIBLE, P), (HIDDEN[0], P), (HIDDEN[1], S)])
    report = validate(challenge, box)
    assert_failed_at(report, StepName.REFERENCE_PASSES, detail="1 of 5 tests do not pass")
    assert f"{HIDDEN[1]} (skipped)" in report.step(StepName.REFERENCE_PASSES).detail


def test_reference_failing_tests_are_named(challenge: Path, box: FakeSandbox) -> None:
    box.runs["reference"] = result([*statuses(VISIBLE, P), (HIDDEN[0], F), (HIDDEN[1], E)])
    report = validate(challenge, box)
    detail = report.step(StepName.REFERENCE_PASSES).detail
    assert_failed_at(report, StepName.REFERENCE_PASSES, detail="2 of 5 tests do not pass")
    assert f"{HIDDEN[0]} (failed)" in detail
    assert f"{HIDDEN[1]} (errored)" in detail


def test_reference_missing_hidden_test_fails(challenge: Path, box: FakeSandbox) -> None:
    box.runs["reference"] = result([*statuses(VISIBLE, P), (HIDDEN[0], P)])
    report = validate(challenge, box)
    assert_failed_at(report, StepName.REFERENCE_PASSES, detail="hidden tests missing")
    assert HIDDEN[1] in report.step(StepName.REFERENCE_PASSES).detail


def test_reference_missing_visible_test_fails(challenge: Path, box: FakeSandbox) -> None:
    box.runs["reference"] = result(statuses(VISIBLE[:2] + HIDDEN, P))
    report = validate(challenge, box)
    assert_failed_at(
        report,
        StepName.REFERENCE_PASSES,
        detail="tests of the starting-state run missing from the reference run: " + VISIBLE[2],
    )


def test_reference_without_tests_fails(challenge: Path, box: FakeSandbox) -> None:
    box.runs["reference"] = result([])
    report = validate(challenge, box)
    assert_failed_at(report, StepName.REFERENCE_PASSES, detail="reported no tests")


@pytest.mark.parametrize(
    ("outcome", "limit"),
    [(RunOutcome.MISSING_RESULTS, None), (RunOutcome.LIMIT_EXCEEDED, "memory")],
)
def test_reference_inconclusive_fails(
    challenge: Path, box: FakeSandbox, outcome: RunOutcome, limit: str | None
) -> None:
    box.runs["reference"] = result([], outcome, limit=limit)
    report = validate(challenge, box)
    assert_failed_at(report, StepName.REFERENCE_PASSES, detail="inconclusive")


def test_patch_that_does_not_apply_fails(challenge: Path, box: FakeSandbox) -> None:
    patch = challenge / "solution" / "reference.patch"
    patch.write_text(patch.read_text().replace("len(items) // per_page", "len(things) // n"))
    report = validate(challenge, box)
    assert_failed_at(report, StepName.REFERENCE_PASSES, detail="does not apply")
    assert "patch failed" in report.step(StepName.REFERENCE_PASSES).detail
    assert "reference" not in [kind for kind, _ in box.calls]


def test_garbage_patch_fails(challenge: Path, box: FakeSandbox) -> None:
    (challenge / "solution" / "reference.patch").write_text("not a patch\n")
    report = validate(challenge, box)
    assert_failed_at(report, StepName.REFERENCE_PASSES, detail="does not apply")


def test_patch_that_changes_nothing_fails(challenge: Path, box: FakeSandbox) -> None:
    (challenge / "solution" / "reference.patch").write_text(
        "diff --git a/src/catalog/pagination.py b/src/catalog/pagination.py\n"
        "--- a/src/catalog/pagination.py\n"
        "+++ b/src/catalog/pagination.py\n"
        "@@ -2,3 +2,3 @@\n"
        " \n"
        "-from __future__ import annotations\n"
        "+from __future__ import annotations\n"
        " \n"
    )
    report = validate(challenge, box)
    assert_failed_at(report, StepName.REFERENCE_PASSES, detail="changed no files")


def test_patch_outside_workspace_is_rejected(challenge: Path, box: FakeSandbox) -> None:
    (challenge / "solution" / "reference.patch").write_text(
        "diff --git a/../escape.txt b/../escape.txt\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/../escape.txt\n"
        "@@ -0,0 +1 @@\n"
        "+escaped\n"
    )
    report = validate(challenge, box)
    assert_failed_at(report, StepName.REFERENCE_PASSES, detail="does not apply")
    assert not (challenge / "escape.txt").exists()


def test_patch_creating_a_check_file_clashes(challenge: Path, box: FakeSandbox) -> None:
    (challenge / "solution" / "reference.patch").write_text(
        "diff --git a/tests/test_pagination.py b/tests/test_pagination.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/tests/test_pagination.py\n"
        "@@ -0,0 +1 @@\n"
        "+x = 1\n"
    )
    report = validate(challenge, box)
    assert_failed_at(report, StepName.REFERENCE_PASSES, detail="'tests/test_pagination.py'")
    assert "checks.visible" in report.step(StepName.REFERENCE_PASSES).detail
    assert "reference" not in [kind for kind, _ in box.calls]


def test_git_missing_is_an_environment_error(
    challenge: Path, box: FakeSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reference_module.shutil, "which", lambda _name: None)
    with pytest.raises(VerifyEnvironmentError, match="git"):
        validate(challenge, box)


# --------------------------------------------------------------------------------------------------
# Determinism and verification.json helpers
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["visible", "hidden", "reference"])
@pytest.mark.parametrize("round_number", [2, 3])
@pytest.mark.parametrize("change", ["status", "id", "missing", "extra", "duplicate", "outcome"])
def test_determinism_rejects_first_changed_run(
    challenge, box, monkeypatch, kind, round_number, change
):
    original = box.run_check
    seen = {key: 0 for key in good_runs()}

    def varying(image, layers, command, *, limits):
        raw = original(image, layers, command, limits=limits)
        current = box.kind(layers)
        seen[current] += 1
        if current != kind or seen[current] != round_number:
            return raw
        tests = list(raw.tests)
        if change == "status":
            tests[0] = replace(tests[0], status=TestStatus.SKIPPED)
        elif change == "id":
            tests[0] = replace(tests[0], id="different-id")
        elif change == "missing":
            tests.pop()
        elif change == "extra":
            tests.append(replace(tests[0], id="extra-id"))
        elif change == "duplicate":
            tests.append(tests[0])
        outcome = RunOutcome.ERRORED if change == "outcome" else raw.outcome
        return replace(raw, tests=tuple(tests), outcome=outcome, log_tail="PRIVATE-RUN-LOG")

    monkeypatch.setattr(box, "run_check", varying)
    (challenge / VERIFICATION_FILE).write_text(STALE_RECORD)
    report = validate(challenge, box)
    assert_failed_at(report, StepName.DETERMINISM, detail="differs from round 1")
    step = report.step(StepName.DETERMINISM)
    expected_runs = 3 * (round_number - 1) + ["visible", "hidden", "reference"].index(kind) + 1
    assert len(step.runs) == expected_runs
    assert len(box.calls) == expected_runs + 1  # exactly one build
    assert step.runs[-1].label.startswith(f"round-{round_number}:")
    assert "PRIVATE-RUN-LOG" not in json.dumps(report.to_dict())


def test_determinism_ignores_test_order(challenge, box, monkeypatch):
    original = box.run_check

    def reordered(image, layers, command, *, limits):
        raw = original(image, layers, command, limits=limits)
        return replace(raw, tests=tuple(reversed(raw.tests))) if len(box.calls) > 4 else raw

    monkeypatch.setattr(box, "run_check", reordered)
    report = validate(challenge, box)
    assert report.valid
    assert len(report.step(StepName.DETERMINISM).runs) == 9
    assert len(box.reference_snapshots) == 3
    assert all(s == box.reference_snapshots[0] for s in box.reference_snapshots)
    copies = [paths[0] for kind, paths in box.calls if kind == "reference"]
    assert len(set(copies)) == 3
    assert all(not path.exists() for path in copies)


@pytest.mark.parametrize("outcome", [RunOutcome.MISSING_RESULTS, RunOutcome.LIMIT_EXCEEDED])
def test_determinism_inconclusive_repeat_is_failed(challenge, box, monkeypatch, outcome):
    original = box.run_check

    def inconclusive(image, layers, command, *, limits):
        raw = original(image, layers, command, limits=limits)
        return (
            replace(raw, outcome=outcome, log_tail="PRIVATE-RUN-LOG")
            if len(box.calls) == 5
            else raw
        )

    monkeypatch.setattr(box, "run_check", inconclusive)
    report = validate(challenge, box)
    assert_failed_at(report, StepName.DETERMINISM, detail="inconclusive")
    assert len(report.step(StepName.DETERMINISM).runs) == 4
    assert "PRIVATE-RUN-LOG" not in json.dumps(report.to_dict())


def test_determinism_engine_failure_stays_environment_error(challenge, box, monkeypatch):
    original = box.run_check

    def unavailable(image, layers, command, *, limits):
        if len(box.calls) == 4:
            raise SandboxError("engine unavailable")
        return original(image, layers, command, limits=limits)

    monkeypatch.setattr(box, "run_check", unavailable)
    with pytest.raises(VerifyEnvironmentError):
        validate(challenge, box)
    assert not (challenge / VERIFICATION_FILE).exists()


def test_determinism_no_write_preserves_existing_record(challenge, box, monkeypatch):
    original = box.run_check

    def changing(image, layers, command, *, limits):
        raw = original(image, layers, command, limits=limits)
        return replace(raw, tests=()) if len(box.calls) == 5 else raw

    monkeypatch.setattr(box, "run_check", changing)
    record = challenge / VERIFICATION_FILE
    record.write_text(STALE_RECORD)
    report = validate(challenge, box, write=False)
    assert report.failed_step is StepName.DETERMINISM
    assert record.read_text() == STALE_RECORD


@pytest.mark.parametrize("variant", ["anti-empty", "anti-deleted", "anti-skipped"])
@pytest.mark.parametrize("change", ["passed", "skipped", "errored", "missing", "duplicate", "new"])
def test_anti_gaming_requires_exact_hidden_evidence(challenge, box, monkeypatch, variant, change):
    original = box.run_check

    def tampered(image, layers, command, *, limits):
        raw = original(image, layers, command, limits=limits)
        if box.kind(layers) != variant:
            return raw
        tests = list(raw.tests)
        index = next(i for i, test in enumerate(tests) if test.id == HIDDEN[0])
        if change in ("passed", "skipped", "errored"):
            tests[index] = replace(tests[index], status=TestStatus(change))
        elif change == "missing":
            tests.pop(index)
        elif change == "duplicate":
            tests.append(tests[index])
        else:
            tests.append(replace(tests[index], id="unexpected-test"))
        return replace(raw, tests=tuple(tests), log_tail="PRIVATE-SYNTHETIC-LOG")

    monkeypatch.setattr(box, "run_check", tampered)
    (challenge / VERIFICATION_FILE).write_text(STALE_RECORD)
    report = validate(challenge, box)
    assert_failed_at(report, StepName.ANTI_GAMING, detail="changed hidden test")
    expected_count = ["anti-empty", "anti-deleted", "anti-skipped"].index(variant) + 1
    assert len(report.step(StepName.ANTI_GAMING).runs) == expected_count
    assert len(box.calls) == 10 + expected_count
    assert "PRIVATE-SYNTHETIC-LOG" not in json.dumps(report.to_dict())
    assert all(not paths[0].exists() for kind, paths in box.calls if kind.startswith("anti-"))


def test_anti_gaming_copies_and_mutates_only_editable_modules(challenge, box, monkeypatch):
    before = reference_module.snapshot(challenge)
    original = box.run_check

    def inspect(image, layers, command, *, limits):
        kind = box.kind(layers)
        if kind.startswith("anti-"):
            assert not layers[0].is_relative_to(challenge)
            assert layers[-1] == challenge.resolve() / "checks/hidden"
            visible = layers[1] / "tests/test_pagination.py"
            if kind == "anti-deleted":
                assert not visible.exists()
            elif kind == "anti-skipped":
                assert "mark.skip" in visible.read_text()
            else:
                assert (
                    visible.read_bytes()
                    == (challenge / "checks/visible/tests/test_pagination.py").read_bytes()
                )
        return original(image, layers, command, limits=limits)

    monkeypatch.setattr(box, "run_check", inspect)
    report = validate(challenge, box, write=False)
    assert report.step(StepName.ANTI_GAMING).status is StepStatus.PASSED
    assert reference_module.snapshot(challenge) == before


@pytest.mark.parametrize("unsupported", ["runner", "modules", "baseline"])
def test_anti_gaming_unsupported_is_never_passed(challenge, box, unsupported):
    if unsupported == "runner":
        manifest = challenge / "challenge.yaml"
        manifest.write_text(
            manifest.read_text().replace("test_command: pytest", "test_command: wrapper")
        )
    elif unsupported == "modules":
        module = challenge / "checks/visible/tests/test_pagination.py"
        module.rename(module.with_name("custom_checks.py"))
    else:
        box.runs["visible"] = result([])
    report = validate(challenge, box)
    assert report.valid
    step = report.step(StepName.ANTI_GAMING)
    assert step.status is StepStatus.NOT_RUN
    assert "not verified:" in step.detail
    assert not step.runs
    assert len(box.calls) == 10


@pytest.mark.parametrize("variant", ["anti-deleted", "anti-skipped"])
def test_anti_gaming_requires_observable_editable_mutation(challenge, box, monkeypatch, variant):
    original = box.run_check

    def unchanged(image, layers, command, *, limits):
        raw = original(image, layers, command, limits=limits)
        if box.kind(layers) == variant:
            return box.runs["hidden"]
        return raw

    monkeypatch.setattr(box, "run_check", unchanged)
    report = validate(challenge, box)
    assert report.step(StepName.ANTI_GAMING).status is StepStatus.NOT_RUN
    assert "did not" in report.step(StepName.ANTI_GAMING).detail


@pytest.mark.parametrize("outcome", [RunOutcome.MISSING_RESULTS, RunOutcome.LIMIT_EXCEEDED])
def test_anti_gaming_inconclusive_is_failure(challenge, box, monkeypatch, outcome):
    original = box.run_check

    def inconclusive(image, layers, command, *, limits):
        raw = original(image, layers, command, limits=limits)
        return replace(raw, outcome=outcome) if box.kind(layers) == "anti-empty" else raw

    monkeypatch.setattr(box, "run_check", inconclusive)
    report = validate(challenge, box)
    assert_failed_at(report, StepName.ANTI_GAMING, detail="inconclusive")


def test_anti_gaming_environment_error_and_cleanup(challenge, box, monkeypatch):
    original = box.run_check
    copies = []

    def unavailable(image, layers, command, *, limits):
        if box.kind(layers) == "anti-empty":
            copies.extend(layers[:-1])
            raise SandboxError("engine unavailable")
        return original(image, layers, command, limits=limits)

    monkeypatch.setattr(box, "run_check", unavailable)
    with pytest.raises(VerifyEnvironmentError):
        validate(challenge, box)
    assert copies and all(not path.exists() for path in copies)
    assert not (challenge / VERIFICATION_FILE).exists()


def test_atomic_write_failure_keeps_previous_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / VERIFICATION_FILE).write_text("previous\n")

    def boom(self: Path, target: Path) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(record_module.Path, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        record_module.write_verification(tmp_path, {"format": "x"})
    assert (tmp_path / VERIFICATION_FILE).read_text() == "previous\n"
    assert [p.name for p in tmp_path.iterdir()] == [VERIFICATION_FILE]


def test_write_verification_format(tmp_path: Path) -> None:
    path = record_module.write_verification(tmp_path, {"b": 1, "a": [1]})
    assert path.read_text() == '{\n  "b": 1,\n  "a": [\n    1\n  ]\n}\n'


@pytest.mark.parametrize(
    "content",
    [
        None,
        "{not json",
        "[]",
        '{"format": "other", "format_version": 1}',
        '{"format": "patchground-verification", "format_version": 99}',
    ],
)
def test_read_verification_rejects_unusable(tmp_path: Path, content: str | None) -> None:
    if content is not None:
        (tmp_path / VERIFICATION_FILE).write_text(content)
    assert read_verification(tmp_path) is None


def test_failure_removes_stale_verification_json(challenge: Path, box: FakeSandbox) -> None:
    stale = challenge / VERIFICATION_FILE
    stale.write_text(STALE_RECORD)
    box.build_error = BuildFailed("boom\n")

    report = validate(challenge, box)

    assert_failed_at(report, StepName.BUILD)
    assert report.removed_verification_file == stale
    assert report.to_dict()["removed_verification_file"] == str(stale)


def test_failure_without_write_keeps_existing_verification_json(
    challenge: Path, box: FakeSandbox
) -> None:
    existing = challenge / VERIFICATION_FILE
    existing.write_text("{}\n")
    box.build_error = BuildFailed("boom\n")

    report = validate(challenge, box, write=False)

    assert not report.valid
    assert report.removed_verification_file is None
    assert existing.exists()


def test_failure_keeps_a_foreign_verification_json(challenge: Path, box: FakeSandbox) -> None:
    foreign = challenge / VERIFICATION_FILE
    foreign.write_text('{"format": "someone-else", "data": 1}\n')
    box.build_error = BuildFailed("boom\n")

    report = validate(challenge, box)

    assert not report.valid
    assert report.removed_verification_file is None
    assert foreign.read_text() == '{"format": "someone-else", "data": 1}\n'


def test_remove_verification_needs_a_challenge_folder(tmp_path: Path) -> None:
    record = tmp_path / VERIFICATION_FILE
    record.write_text(STALE_RECORD)
    assert record_module.remove_verification(tmp_path) is None
    assert record.exists()
    (tmp_path / "challenge.yaml").write_text("id: x\n")
    assert record_module.remove_verification(tmp_path) == record
    assert not record.exists()


def test_unwritable_verification_json_is_an_environment_error(
    challenge: Path, box: FakeSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(root: Path, document: object) -> Path:
        raise PermissionError(13, "Permission denied", str(root / VERIFICATION_FILE))

    monkeypatch.setattr(validate_module, "write_verification", denied)
    with pytest.raises(VerifyEnvironmentError, match=r"could not be written: .*Permission denied"):
        validate(challenge, box)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unremovable_stale_record_is_an_environment_error(
    challenge: Path, box: FakeSandbox
) -> None:
    (challenge / VERIFICATION_FILE).write_text(STALE_RECORD)
    box.build_error = BuildFailed("boom\n")
    challenge.chmod(0o555)
    try:
        with pytest.raises(VerifyEnvironmentError, match=r"failed at step build .* not be removed"):
            validate(challenge, box)
    finally:
        challenge.chmod(0o755)
    assert (challenge / VERIFICATION_FILE).exists()


def test_workspace_copy_failure_is_an_environment_error(
    challenge: Path, box: FakeSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_copytree(*args: object, **kwargs: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(reference_module.shutil, "copytree", broken_copytree)
    with pytest.raises(VerifyEnvironmentError, match="could not copy the workspace"):
        validate(challenge, box)


def test_planted_git_filter_never_runs_even_if_the_loader_missed_it(
    challenge: Path, box: FakeSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Defence in depth: bypass the loader's .git check and run the full pipeline.
    monkeypatch.setattr(loader_module, "_git_entries", lambda _directory: [])
    workspace = challenge / "workspace"
    marker = tmp_path / "pwned"
    subprocess.run(["git", "init", "-q", str(workspace)], check=True, capture_output=True)
    for key in ("filter.x.clean", "filter.x.smudge"):
        subprocess.run(
            ["git", "-C", str(workspace), "config", key, f"touch {marker}; cat"], check=True
        )
    (workspace / ".gitattributes").write_text("* filter=x\n")
    report = validate(challenge, box, write=False)
    assert report.step(StepName.REFERENCE_PASSES).status is StepStatus.PASSED
    assert not marker.exists()
    assert box.reference_snapshots
    assert not any(path.split("/")[0] == ".git" for path in box.reference_snapshots[0])
