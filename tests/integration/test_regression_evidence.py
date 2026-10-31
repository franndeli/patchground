"""Real Docker regression evidence: learner tests run alone on original and final code."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from patchground.report.regression import RegressionEvidence, evaluate_regression
from patchground.sandbox import BuildResult, SandboxError, TestStatus, build_image

pytestmark = pytest.mark.docker

COMMAND = "python -m pytest -q -p no:cacheprovider --junitxml=$PG_RESULTS/junit.xml"
BROKEN = "def total(prices):\n    return sum(prices[1:])\n"
FIXED = "def total(prices):\n    return sum(prices)\n"
# Unchanged by the learner: fails on the original code only because of the bug.
EXISTING = """\
from shop.pricing import total


def test_existing_total():
    assert total([1, 2]) == 3
"""
NEW_FAILING = """

def test_new_total():
    assert total([5, 5]) == 10
"""
NEW_PASSING = """

def test_new_empty():
    assert total([]) == 0
"""


@pytest.fixture(scope="module")
def image(tmp_path_factory: pytest.TempPathFactory) -> BuildResult:
    env = tmp_path_factory.mktemp("environment")
    (env / "Dockerfile").write_text(
        "FROM python:3.12-slim\nENV PYTHONDONTWRITEBYTECODE=1\n"
        "RUN pip install --no-cache-dir pytest==8.3.5\n"
    )
    return build_image(env / "Dockerfile", name="regression-test")


def tree(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(content))
    return root


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def evaluate(
    tmp_path: Path,
    image: BuildResult,
    tests: str,
    *,
    original_tests: str = EXISTING,
    extra: dict[str, str] | None = None,
    command: str = COMMAND,
) -> RegressionEvidence:
    original = tree(
        tmp_path / "original", {"shop/pricing.py": BROKEN, "tests/test_total.py": original_tests}
    )
    final = tree(
        tmp_path / "final",
        {"shop/pricing.py": FIXED, "tests/test_total.py": tests, **(extra or {})},
    )
    kept = (snapshot(original), snapshot(final))
    evidence = evaluate_regression(original, final, image.image_id, command)
    assert (snapshot(original), snapshot(final)) == kept
    return evidence


def test_before_fails_after_passes(tmp_path: Path, image: BuildResult) -> None:
    evidence = evaluate(tmp_path, image, EXISTING + NEW_FAILING + NEW_PASSING)
    assert evidence.status == "verified", evidence.reason
    new = "tests.test_total::test_new_total"
    assert evidence.candidates == (new, "tests.test_total::test_new_empty")
    # The pre-existing failure (fixed by the code change) and the already-passing addition
    # never count as the learner's regression test.
    assert evidence.verified_tests == (new,)
    assert [(t.id, t.status) for t in evidence.before_tests] == [
        (new, TestStatus.FAILED),
        ("tests.test_total::test_new_empty", TestStatus.PASSED),
    ]
    assert all(t.status == TestStatus.PASSED for t in evidence.after_tests)
    assert (evidence.before_outcome, evidence.after_outcome) == ("failed", "passed")


def test_unchanged_pre_existing_failure_is_not_a_regression_test(
    tmp_path: Path, image: BuildResult
) -> None:
    evidence = evaluate(tmp_path, image, EXISTING + NEW_PASSING)
    assert evidence.status == "not_verified"
    assert evidence.verified_tests == ()
    assert "test_existing_total" not in evidence.model_dump_json()


def test_unfixed_new_test_is_not_verified(tmp_path: Path, image: BuildResult) -> None:
    final = EXISTING + "\n\ndef test_still_wrong():\n    assert total([1]) == 2\n"
    evidence = evaluate(tmp_path, image, final)
    assert evidence.status == "not_verified"
    assert evidence.verified_tests == ()
    assert evidence.before_outcome == "failed" and evidence.after_outcome == "failed"


def test_collection_error_before_is_not_verified(tmp_path: Path, image: BuildResult) -> None:
    final = "from shop.pricing import total, missing_before\n\n\ndef test_x():\n    assert True\n"
    evidence = evaluate(tmp_path, image, final)
    assert evidence.status == "not_verified"
    assert evidence.verified_tests == ()
    assert "Traceback" not in evidence.model_dump_json()


def test_skipped_new_test_is_not_verified(tmp_path: Path, image: BuildResult) -> None:
    skipped = "\n\nimport pytest\n\n\n@pytest.mark.skip\ndef test_skipped():\n    assert False\n"
    evidence = evaluate(tmp_path, image, EXISTING + skipped)
    assert evidence.status == "not_verified"
    assert [t.status for t in evidence.before_tests] == [TestStatus.SKIPPED]


def test_deleted_tests_have_no_candidates(tmp_path: Path, image: BuildResult) -> None:
    evidence = evaluate(tmp_path, image, "", original_tests=EXISTING + NEW_FAILING)
    assert evidence.status == "not_verified"
    assert evidence.before_outcome is None


def test_harness_changes_and_unsupported_commands_are_not_established(
    tmp_path: Path, image: BuildResult
) -> None:
    tests = EXISTING + NEW_FAILING
    changed = evaluate(tmp_path / "a", image, tests, extra={"conftest.py": "A = 1\n"})
    assert changed.status == "not_established"
    shell = evaluate(tmp_path / "b", image, tests, command="make test")
    assert shell.status == "not_established"
    collection = evaluate(tmp_path / "c", image, tests, command=COMMAND + " -k total")
    assert collection.status == "not_established"
    assert changed.before_outcome is None


def test_engine_failures_raise_for_retry(tmp_path: Path, image: BuildResult) -> None:
    original = tree(
        tmp_path / "original", {"shop/pricing.py": BROKEN, "tests/test_total.py": EXISTING}
    )
    final = tree(
        tmp_path / "final",
        {"shop/pricing.py": FIXED, "tests/test_total.py": EXISTING + NEW_FAILING},
    )
    with pytest.raises(SandboxError):
        evaluate_regression(original, final, "sha256:" + "0" * 64, COMMAND)
