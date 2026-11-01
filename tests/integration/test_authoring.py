from pathlib import Path

import pytest

from patchground.authoring import create_challenge
from patchground.verify import StepStatus, validate_challenge

pytestmark = pytest.mark.docker


@pytest.mark.parametrize("language", ["python", "typescript"])
@pytest.mark.parametrize("type_", ["debug", "feature"])
def test_unedited_starter_passes_all_validation_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str, type_: str
) -> None:
    monkeypatch.chdir(tmp_path)
    created = create_challenge("fresh-starter", language=language, type_=type_)
    report = validate_challenge(tmp_path / created.path, write=False)
    assert report.valid, [(step.name, step.status) for step in report.steps]
    assert len(report.steps) == 6
    assert all(step.status is StepStatus.PASSED for step in report.steps)


@pytest.mark.parametrize(
    "name",
    [
        "duplicate-charges-on-retry",
        "cache-expiry",
        "csv-import-row-errors",
        "release-version-ordering",
        "event-bus-subscriptions",
    ],
)
def test_curated_challenge_passes_all_gates(name: str) -> None:
    root = Path(__file__).resolve().parents[2] / "examples" / name
    report = validate_challenge(root, write=False)
    assert report.valid, [(step.name, step.status) for step in report.steps]
    assert len(report.steps) == 6
    assert all(step.status is StepStatus.PASSED for step in report.steps)
