"""End-to-end validation of the example challenge and the broken fixtures against Docker."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from patchground.sandbox import Limits, RunOutcome, RunResult, TestStatus
from patchground.verify import VERIFICATION_FILE, StepName, StepStatus, validate_challenge
from patchground.verify.validate import DockerSandbox

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
    deterministic = report.step(StepName.DETERMINISM)
    assert deterministic.status is StepStatus.PASSED
    assert len(deterministic.runs) == 9
    assert len({run.label for run in deterministic.runs}) == 9
    anti = report.step(StepName.ANTI_GAMING)
    assert anti.status is StepStatus.PASSED
    assert [run.label for run in anti.runs] == ["anti-empty", "anti-deleted", "anti-skipped"]
    assert anti.runs[1].count(TestStatus.FAILED) == 3
    assert anti.runs[2].count(TestStatus.SKIPPED) == 5


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
    assert doc["steps"][4]["status"] == "passed"
    assert len(doc["steps"][4]["runs"]) == 9
    assert doc["steps"][5]["status"] == "passed"
    assert len(doc["steps"][5]["runs"]) == 3


def test_real_container_rejects_editable_test_deletion_bypass(tmp_path: Path) -> None:
    source = tmp_path / EXAMPLE.name
    shutil.copytree(EXAMPLE, source, ignore=shutil.ignore_patterns(VERIFICATION_FILE))
    hook = source / "workspace/conftest.py"
    hook.write_text(
        "from pathlib import Path\n"
        "def pytest_collection_modifyitems(items):\n"
        "    if not Path('tests/test_pagination.py').exists():\n"
        "        for item in items:\n"
        "            item.obj = lambda **kwargs: None\n"
    )
    before = hook.read_bytes()
    report = validate_challenge(source)
    assert report.failed_step is StepName.ANTI_GAMING
    anti = report.step(StepName.ANTI_GAMING)
    assert [run.label for run in anti.runs] == ["anti-empty", "anti-deleted"]
    assert anti.runs[-1].outcome is RunOutcome.PASSED
    assert "changed hidden" in anti.detail
    assert hook.read_bytes() == before
    assert not (source / VERIFICATION_FILE).exists()


def test_real_container_detects_changing_test_identity(tmp_path: Path) -> None:
    source = tmp_path / EXAMPLE.name
    shutil.copytree(EXAMPLE, source, ignore=shutil.ignore_patterns(VERIFICATION_FILE))
    marker = source / "workspace/tests/test_run_marker.py"
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(
        "import os\nimport pytest\n"
        '@pytest.mark.parametrize("round_number", [os.environ["PATCHGROUND_TEST_ROUND"]])\n'
        "def test_run_marker(round_number):\n    assert round_number\n"
    )
    before = marker.read_bytes()

    class VaryingEnvironment(DockerSandbox):
        calls = 0

        def run_check(
            self, image_id: str, layers: Sequence[Path], command: str, *, limits: Limits
        ) -> RunResult:
            round_number = self.calls // 3 + 1
            self.calls += 1
            return super().run_check(
                image_id,
                layers,
                f"export PATCHGROUND_TEST_ROUND={round_number}; {command}",
                limits=limits,
            )

    sandbox = VaryingEnvironment()
    report = validate_challenge(source, sandbox=sandbox)
    assert report.failed_step is StepName.DETERMINISM
    assert "round-2:workspace+visible" in report.step(StepName.DETERMINISM).detail
    assert sandbox.calls == 4
    assert marker.read_bytes() == before
    assert not (source / VERIFICATION_FILE).exists()
