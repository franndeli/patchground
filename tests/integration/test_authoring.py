from collections import Counter
from pathlib import Path

import pytest

from patchground.authoring import create_challenge
from patchground.sessions import check_session, start_session
from patchground.spec import load_challenge
from patchground.verify import StepName, StepStatus, validate_challenge

pytestmark = pytest.mark.docker
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
CURATED = sorted(path.parent.name for path in EXAMPLES.glob("*/challenge.yaml"))


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


@pytest.mark.parametrize("name", CURATED)
def test_curated_challenge_passes_all_gates(name: str, tmp_path: Path) -> None:
    source = EXAMPLES / name
    report = validate_challenge(source, write=False)
    assert report.valid, [(step.name, step.status) for step in report.steps]
    assert len(report.steps) == 6
    assert all(step.status is StepStatus.PASSED for step in report.steps)
    baseline = next(step for step in report.steps if step.name is StepName.BROKEN_FAILS)
    visible, combined = baseline.runs
    assert {test.id for test in combined.tests} - {test.id for test in visible.tests}

    manifest = load_challenge(source).manifest
    layers = [source / "workspace"]
    if manifest.checks.visible is not None:
        layers.append(source / manifest.checks.visible)
    expected = {p.relative_to(layer) for layer in layers for p in layer.rglob("*") if p.is_file()}
    started = start_session(source, root=tmp_path / "sessions")
    git = started.workspace / ".git"
    before = {p.relative_to(git): p.read_bytes() for p in git.rglob("*") if p.is_file()}
    result = check_session(started.session, root=tmp_path / "sessions")
    assert result.counts["failed"] > 0
    assert result.counts["errored"] == 0
    assert not result.passed
    assert Counter((test.id, test.status) for test in result.tests) == Counter(
        (test.id, test.status) for test in combined.tests
    )
    assert {p.relative_to(git): p.read_bytes() for p in git.rglob("*") if p.is_file()} == before
    actual = {
        p.relative_to(started.workspace)
        for p in started.workspace.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(started.workspace).parts
    }
    assert actual == expected
