from collections.abc import Sequence
from pathlib import Path

import pytest

from patchground.authoring import create_challenge
from patchground.sandbox import BuildResult, RunOutcome, RunResult, TestResult, TestStatus
from patchground.sessions import start_session


class FakeSandbox:
    def __init__(self) -> None:
        self.runs = 0
        self.error: BaseException | None = None
        self.result = RunResult(
            RunOutcome.PASSED,
            (TestResult("fixture::case", "case", "fixture", TestStatus.PASSED),),
            0,
            None,
            "PRIVATE-RAW-LOG",
        )

    def build_image(self, dockerfile: Path, *, name: str) -> BuildResult:
        return BuildResult("sha256:fixture", "fixture", "")

    def run_check(self, image_id: str, layers: Sequence[Path], command: str) -> RunResult:
        self.runs += 1
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def sandbox() -> FakeSandbox:
    return FakeSandbox()


@pytest.fixture
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sandbox: FakeSandbox) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    created = create_challenge("report-fixture")
    return start_session(tmp_path / created.path, sandbox=sandbox).session
