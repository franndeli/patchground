"""Regression evidence with a fake sandbox: selection, honesty rules and fault handling."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from textwrap import dedent

import pytest

from patchground.report.regression import RegressionEvidence, evaluate_regression
from patchground.sandbox import RunOutcome, RunResult, SandboxError, TestResult, TestStatus

COMMAND = "pytest -q -p no:cacheprovider --junitxml=$PG_RESULTS/junit.xml"
CODE = "def fee(n):\n    return n\n"
FIXED = "def fee(n):\n    return n + 1\n"
OLD_TEST = "def test_old():\n    assert True\n"
NEW_TEST = "\ndef test_new():\n    assert True\n"


def write(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(content))
    root.mkdir(exist_ok=True)
    return root


def result(test_id: str, status: TestStatus) -> TestResult:
    classname, _, name = test_id.partition("::")
    return TestResult(test_id, name, classname, status)


def run(*tests: tuple[str, TestStatus], outcome: RunOutcome | None = None) -> RunResult:
    results = tuple(result(*t) for t in tests)
    if outcome is None:
        statuses = {t.status for t in results}
        outcome = (
            RunOutcome.ERRORED
            if not results or TestStatus.ERRORED in statuses
            else RunOutcome.FAILED
            if TestStatus.FAILED in statuses
            else RunOutcome.PASSED
        )
    return RunResult(outcome, results, 0, None, "SECRET raw log")


class FakeSandbox:
    def __init__(self, *runs: RunResult | Exception) -> None:
        self.runs = list(runs)
        self.calls: list[tuple[dict[str, str], str]] = []

    def run_check(self, image_id: str, layers: Sequence[Path], command: str) -> RunResult:
        assert image_id == "sha256:image"
        (layer,) = layers
        snapshot = {
            p.relative_to(layer).as_posix(): p.read_text() for p in layer.rglob("*") if p.is_file()
        }
        self.calls.append((snapshot, command))
        outcome = self.runs.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def evaluate(
    tmp_path: Path,
    original: dict[str, str],
    final: dict[str, str],
    *runs: RunResult | Exception,
    command: str = COMMAND,
) -> tuple[RegressionEvidence, FakeSandbox]:
    box = FakeSandbox(*runs)
    evidence = evaluate_regression(
        write(tmp_path / "original", original),
        write(tmp_path / "final", final),
        "sha256:image",
        command,
        sandbox=box,
    )
    return evidence, box


ORIGINAL = {"app.py": CODE, "tests/test_app.py": OLD_TEST}
FINAL = {"app.py": FIXED, "tests/test_app.py": OLD_TEST + NEW_TEST}
NEW = "tests.test_app::test_new"
FAIL, PASS = TestStatus.FAILED, TestStatus.PASSED


@pytest.mark.parametrize("parameter", ["x" * 250, "line\nbreak"])
def test_unsafe_display_identity_cannot_be_verified(tmp_path: Path, parameter: str) -> None:
    identity = f"{NEW}[{parameter}]"
    evidence, _ = evaluate(tmp_path, ORIGINAL, FINAL, run((identity, FAIL)), run((identity, PASS)))
    assert evidence.status == "not_established"
    assert evidence.verified_tests == ()


def test_frozen_testpaths_allow_explicit_candidate_selection(tmp_path: Path) -> None:
    config = {"pyproject.toml": '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'}
    evidence, _ = evaluate(
        tmp_path, ORIGINAL | config, FINAL | config, run((NEW, FAIL)), run((NEW, PASS))
    )
    assert evidence.status == "verified"


@pytest.mark.parametrize("phase", ["before", "after"])
def test_inconsistent_runner_outcome_cannot_verify(tmp_path: Path, phase: str) -> None:
    before = run((NEW, FAIL), outcome=RunOutcome.ERRORED) if phase == "before" else run((NEW, FAIL))
    after = run((NEW, PASS), outcome=RunOutcome.FAILED) if phase == "after" else run((NEW, PASS))
    evidence, _ = evaluate(tmp_path, ORIGINAL, FINAL, before, after)
    assert evidence.status != "verified"
    assert not evidence.verified_tests


def test_verified_when_the_new_test_fails_before_and_passes_after(tmp_path: Path) -> None:
    evidence, box = evaluate(tmp_path, ORIGINAL, FINAL, run((NEW, FAIL)), run((NEW, PASS)))
    assert evidence.status == "verified"
    assert evidence.candidates == (NEW,)
    assert evidence.verified_tests == (NEW,)
    assert [(t.id, t.status) for t in evidence.before_tests] == [(NEW, FAIL)]
    assert [(t.id, t.status) for t in evidence.after_tests] == [(NEW, PASS)]
    assert (evidence.before_outcome, evidence.after_outcome) == ("failed", "passed")
    assert "SECRET" not in evidence.model_dump_json()
    (before_files, before_cmd), (after_files, after_cmd) = box.calls
    assert before_cmd == after_cmd
    assert before_cmd == (
        "pytest -q -p no:cacheprovider --rootdir=. --junitxml=$PG_RESULTS/junit.xml "
        "tests/test_app.py::test_new"
    )
    # Same learner test material, original code on one side and final code on the other.
    assert before_files["tests/test_app.py"] == after_files["tests/test_app.py"]
    assert before_files["app.py"] == CODE
    assert after_files["app.py"] == FIXED


def test_only_new_or_changed_definitions_are_selected(tmp_path: Path) -> None:
    original = {"tests/test_a.py": "def test_keep():\n    assert False  # known failure\n"}
    final = {
        "tests/test_a.py": (
            "# reformatted\ndef test_keep():\n    assert False  # known failure\n"
            "\n\nclass TestBox:\n    def test_method(self):\n        assert True\n"
            "\n\ndef test_kept_but_edited():\n    assert 1 == 1\n"
        ),
    }
    original["tests/test_a.py"] += "def test_kept_but_edited():\n    assert 1 == 2\n"
    ident = "tests.test_a.TestBox::test_method"
    edited = "tests.test_a::test_kept_but_edited"
    evidence, box = evaluate(
        tmp_path,
        original,
        final,
        run((ident, FAIL), (edited, FAIL)),
        run((ident, PASS), (edited, PASS)),
    )
    assert evidence.status == "verified"
    assert evidence.candidates == (ident, edited)
    assert "test_keep" not in box.calls[0][1]
    assert box.calls[0][1].endswith(
        "tests/test_a.py::TestBox::test_method tests/test_a.py::test_kept_but_edited"
    )


def test_unchanged_failing_test_in_a_modified_module_cannot_establish_regression(
    tmp_path: Path,
) -> None:
    old = "from app import fee\n\n\ndef test_old():\n    assert fee(1) == 2\n"
    final = {"app.py": FIXED, "tests/test_app.py": old + NEW_TEST}
    original = {"app.py": CODE, "tests/test_app.py": old}
    evidence, box = evaluate(tmp_path, original, final, run((NEW, PASS)), run((NEW, PASS)))
    # test_old failed before and passes after, but it is unchanged and therefore not selected.
    assert evidence.status == "not_verified"
    assert evidence.verified_tests == ()
    assert box.calls[0][1].endswith(" tests/test_app.py::test_new")
    assert evidence.reason == "selected tests already pass on the original code"
    assert len(box.calls) == 1


def test_only_failing_individual_parameters_are_verified(tmp_path: Path) -> None:
    final = {"app.py": FIXED, "tests/test_app.py": OLD_TEST + NEW_TEST}
    a, b = f"{NEW}[a]", f"{NEW}[b]"
    evidence, _ = evaluate(
        tmp_path,
        ORIGINAL,
        final,
        run((a, FAIL), (b, PASS)),
        run((a, PASS), (b, PASS)),
    )
    assert evidence.status == "verified"
    assert evidence.verified_tests == (a,)


def test_every_selected_final_test_must_pass(tmp_path: Path) -> None:
    final = {"tests/test_app.py": OLD_TEST + NEW_TEST + "\ndef test_other():\n    pass\n"}
    other = "tests.test_app::test_other"
    evidence, _ = evaluate(
        tmp_path,
        {"tests/test_app.py": OLD_TEST},
        final,
        run((NEW, FAIL), (other, PASS)),
        run((NEW, PASS), (other, FAIL)),
    )
    assert evidence.status == "not_verified"
    assert evidence.verified_tests == ()
    assert "does not pass on the final" in evidence.reason


def test_errors_skips_and_collection_failures_before_are_not_verified(tmp_path: Path) -> None:
    for before in (
        run((NEW, TestStatus.SKIPPED)),
        run((NEW, TestStatus.ERRORED)),
        run(("tests.test_app::", TestStatus.ERRORED)),  # collection error, candidate absent
        run((NEW, FAIL), ("tests.test_app::test_old", FAIL)),  # unexpected extra test
    ):
        evidence, box = evaluate(tmp_path / str(id(before)), ORIGINAL, FINAL, before)
        assert evidence.status == "not_verified", evidence.reason
        assert evidence.after_tests == () and len(box.calls) == 1


def test_skipped_or_missing_final_tests_are_not_verified(tmp_path: Path) -> None:
    for after in (run((NEW, TestStatus.SKIPPED)), run(("tests.test_other::test_x", PASS))):
        evidence, _ = evaluate(tmp_path / str(id(after)), ORIGINAL, FINAL, run((NEW, FAIL)), after)
        assert evidence.status == "not_verified", evidence.reason
        assert evidence.verified_tests == ()


def test_identity_multiplicity_must_match(tmp_path: Path) -> None:
    evidence, _ = evaluate(
        tmp_path,
        ORIGINAL,
        FINAL,
        run((f"{NEW}[a]", FAIL)),
        run((f"{NEW}[a]", PASS), (f"{NEW}[b]", PASS)),
    )
    assert evidence.status == "not_verified"
    assert "identities differ" in evidence.reason


def test_removed_and_unchanged_tests_have_no_candidates(tmp_path: Path) -> None:
    both = {"tests/test_app.py": OLD_TEST + NEW_TEST}
    evidence, box = evaluate(tmp_path / "deleted", both, {"tests/test_app.py": OLD_TEST})
    assert evidence.status == "not_verified" and not box.calls
    evidence, _ = evaluate(tmp_path / "gone", both, {"app.py": CODE})
    assert evidence.status == "not_verified"
    evidence, _ = evaluate(tmp_path / "same", ORIGINAL, ORIGINAL)
    assert evidence.status == "not_verified"
    assert "no new or changed test definitions" in evidence.reason


@pytest.mark.parametrize("outcome", [RunOutcome.LIMIT_EXCEEDED, RunOutcome.MISSING_RESULTS])
def test_inconclusive_runs_are_not_established(tmp_path: Path, outcome: RunOutcome) -> None:
    evidence, _ = evaluate(tmp_path, ORIGINAL, FINAL, run(outcome=outcome))
    assert evidence.status == "not_established"
    assert evidence.before_outcome == outcome.value
    evidence, _ = evaluate(
        tmp_path / "after", ORIGINAL, FINAL, run((NEW, FAIL)), run(outcome=outcome)
    )
    assert evidence.status == "not_established"
    assert evidence.verified_tests == ()


def test_engine_faults_propagate_for_retry(tmp_path: Path) -> None:
    with pytest.raises(SandboxError):
        evaluate(tmp_path, ORIGINAL, FINAL, SandboxError("engine lost"))
    with pytest.raises(SandboxError):
        evaluate(tmp_path / "late", ORIGINAL, FINAL, run((NEW, FAIL)), SandboxError("lost"))


@pytest.mark.parametrize(
    "command",
    [
        "npm test",
        "uv run pytest",
        "pytest -q | tee out",
        "pytest -q",  # no JUnit target
        "pytest -k fast --junitxml=$PG_RESULTS/junit.xml",
        "pytest -x --junitxml=$PG_RESULTS/junit.xml",
        "pytest --maxfail=1 --junitxml=$PG_RESULTS/junit.xml",
        "pytest --deselect tests/test_app.py::test_old --junitxml=$PG_RESULTS/junit.xml",
        "pytest -o python_files=x.py --junitxml=$PG_RESULTS/junit.xml",
        "pytest -p xdist --junitxml=$PG_RESULTS/junit.xml",
        "pytest -n 4 --junitxml=$PG_RESULTS/junit.xml",
        "pytest --junitxml=/tmp/other.xml",
        "pytest tests/test_app.py::test_old --junitxml=$PG_RESULTS/junit.xml",
        "pytest other --junitxml=$PG_RESULTS/junit.xml",
        "pytest ../up --junitxml=$PG_RESULTS/junit.xml",
    ],
)
def test_unsupported_commands_are_not_established(tmp_path: Path, command: str) -> None:
    evidence, box = evaluate(tmp_path, ORIGINAL, FINAL, command=command)
    assert evidence.status == "not_established", evidence.reason
    assert not box.calls and evidence.verified_tests == ()


def test_supported_positional_paths_and_frozen_options_are_preserved(tmp_path: Path) -> None:
    command = "python -m pytest -q -rA --tb=short tests/ --junitxml $PG_RESULTS/junit.xml"
    evidence, box = evaluate(
        tmp_path, ORIGINAL, FINAL, run((NEW, FAIL)), run((NEW, PASS)), command=command
    )
    assert evidence.status == "verified"
    assert box.calls[0][1].startswith("python -m pytest -q -rA --tb=short --rootdir=. --junitxml=")


def edited(files: dict[str, str]) -> dict[str, str]:
    return {**FINAL, **files}


@pytest.mark.parametrize(
    ("original", "final"),
    [
        (ORIGINAL, edited({"conftest.py": "import pytest\n"})),
        (
            {**ORIGINAL, "conftest.py": "A = 1\n"},
            edited({"conftest.py": "A = 2\n"}),
        ),
        (ORIGINAL, edited({"pytest.ini": "[pytest]\nmarkers = slow\n"})),
        (ORIGINAL, edited({"pyproject.toml": "[project]\nname = 'x'\n"})),
        (
            {**ORIGINAL, "pytest.ini": "[pytest]\naddopts = -k fast\n"},
            {**FINAL, "pytest.ini": "[pytest]\naddopts = -k fast\n"},
        ),
        (
            {**ORIGINAL, "pyproject.toml": "[tool.pytest.ini_options]\npython_files = ['*.py']\n"},
            {**FINAL, "pyproject.toml": "[tool.pytest.ini_options]\npython_files = ['*.py']\n"},
        ),
        (
            {**ORIGINAL, "tests/conftest.py": "def pytest_collection_modifyitems(items): ...\n"},
            {**FINAL, "tests/conftest.py": "def pytest_collection_modifyitems(items): ...\n"},
        ),
        (ORIGINAL, edited({"tests/helpers.py": "VALUE = 1\n"})),
        (ORIGINAL, edited({"tests/data/cases.json": "{}\n"})),
        (
            {"test_root.py": OLD_TEST, "helper.py": "A = 1\n"},
            {"test_root.py": OLD_TEST + NEW_TEST, "helper.py": "A = 2\n"},
        ),
        (
            {**ORIGINAL, "tests/helpers.py": "VALUE = 1\n"},
            {k: v for k, v in FINAL.items()},
        ),
    ],
)
def test_collection_and_harness_changes_are_not_established(
    tmp_path: Path, original: dict[str, str], final: dict[str, str]
) -> None:
    evidence, box = evaluate(tmp_path, original, final)
    assert evidence.status == "not_established", evidence.reason
    assert not box.calls and evidence.verified_tests == ()


def test_changed_helper_without_candidates_stays_not_verified(tmp_path: Path) -> None:
    evidence, _ = evaluate(tmp_path, ORIGINAL, {**ORIGINAL, "tests/helpers.py": "A = 1\n"})
    assert evidence.status == "not_verified"


def test_unrelated_sources_and_noise_do_not_block(tmp_path: Path) -> None:
    final = {
        **FINAL,
        "docs/notes.md": "x\n",
        "tests/__pycache__/junk.pyc": "x",
        ".git/config": "x",
    }
    evidence, box = evaluate(tmp_path, ORIGINAL, final, run((NEW, FAIL)), run((NEW, PASS)))
    assert evidence.status == "verified"
    assert not any("junk" in name or ".git" in name for name in box.calls[0][0])


def test_ambiguous_or_unsupported_sources_are_not_established(tmp_path: Path) -> None:
    cases = {
        "dup": "def test_a():\n    pass\n\ndef test_a():\n    pass\n",
        "syntax": "def test_a(:\n",
    }
    for name, source in cases.items():
        evidence, box = evaluate(
            tmp_path / name, ORIGINAL, {**ORIGINAL, "tests/test_app.py": source}
        )
        assert evidence.status == "not_established", name
        assert not box.calls


def test_symlinks_and_bad_trees_are_not_established(tmp_path: Path) -> None:
    original = write(tmp_path / "original", ORIGINAL)
    final = write(tmp_path / "final", FINAL)
    (final / "link").symlink_to(final / "app.py")
    box = FakeSandbox()
    evidence = evaluate_regression(original, final, "sha256:image", COMMAND, sandbox=box)
    assert evidence.status == "not_established" and not box.calls
    missing = evaluate_regression(original, tmp_path / "nope", "sha256:image", COMMAND, sandbox=box)
    assert missing.status == "not_established"


def test_inputs_are_never_modified(tmp_path: Path) -> None:
    def snapshot(root: Path) -> dict[str, tuple[str, int]]:
        return {
            p.relative_to(root).as_posix(): (p.read_text(), p.stat().st_mtime_ns)
            for p in root.rglob("*")
            if p.is_file()
        }

    write(tmp_path / "original", ORIGINAL)
    write(tmp_path / "final", FINAL)
    before = (snapshot(tmp_path / "original"), snapshot(tmp_path / "final"))
    evaluate_regression(
        tmp_path / "original",
        tmp_path / "final",
        "sha256:image",
        COMMAND,
        sandbox=FakeSandbox(run((NEW, FAIL)), run((NEW, PASS))),
    )
    assert before == (snapshot(tmp_path / "original"), snapshot(tmp_path / "final"))
    assert not list(tmp_path.glob("patchground-regression-*"))


def test_scratch_copies_are_removed_after_faults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "scratch"))
    (tmp_path / "scratch").mkdir()
    with pytest.raises(SandboxError):
        evaluate(tmp_path / "t", ORIGINAL, FINAL, SandboxError("lost"))
    assert list((tmp_path / "scratch").iterdir()) == []
