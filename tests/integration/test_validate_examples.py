"""End-to-end validation of the example challenge and the broken fixtures against Docker."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from patchground.verify import VERIFICATION_FILE, StepName, StepStatus, validate_challenge

pytestmark = pytest.mark.docker

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "pagination-last-page"


def _state(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def test_example_is_valid() -> None:
    before = _state(EXAMPLE / VERIFICATION_FILE)
    report = validate_challenge(EXAMPLE, write=False)
    assert report.valid, [step.detail for step in report.steps]
    assert report.image_id
    assert report.verification_file is None
    assert _state(EXAMPLE / VERIFICATION_FILE) == before
    broken = report.step(StepName.BROKEN_FAILS)
    assert len(broken.runs) == 2
    reference = report.step(StepName.REFERENCE_PASSES)
    assert reference.status is StepStatus.PASSED


@pytest.mark.parametrize(
    ("fixture", "step"),
    [
        ("invalid-manifest", StepName.MANIFEST),
        ("services-unsupported", StepName.MANIFEST),
        ("build-fails", StepName.BUILD),
        ("broken-state-passes", StepName.BROKEN_FAILS),
        ("reference-fails", StepName.REFERENCE_PASSES),
    ],
)
def test_fixture_fails_at_step(fixture: str, step: StepName) -> None:
    folder = REPO / "tests" / "fixtures" / fixture
    report = validate_challenge(folder, write=False)
    assert report.failed_step is step, [s.detail for s in report.steps]
    assert not (folder / VERIFICATION_FILE).exists()


def test_reference_fails_names_the_failing_tests() -> None:
    report = validate_challenge(REPO / "tests" / "fixtures" / "reference-fails", write=False)
    detail = report.step(StepName.REFERENCE_PASSES).detail
    for name in (
        "test_partial_last_page_is_reachable",
        "test_total_pages_rounds_up",
        "test_second_to_last_page_has_next",
    ):
        assert name in detail


def test_cli_end_to_end_json() -> None:
    completed = subprocess.run(
        ["uv", "run", "pgnd", "validate", "examples/pagination-last-page", "--json", "--no-write"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    doc = json.loads(completed.stdout)
    assert doc["valid"] is True
    assert doc["failed_step"] is None
    assert doc["verification_file"] is None
