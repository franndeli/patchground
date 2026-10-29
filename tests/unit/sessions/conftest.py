"""Small authored fixtures and an injected sandbox; no Docker required."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from patchground.sandbox import BuildResult, RunOutcome, RunResult, TestResult, TestStatus


class FakeSandbox:
    def __init__(self) -> None:
        self.builds = 0
        self.runs = 0
        self.error: BaseException | None = None
        self.result = RunResult(
            RunOutcome.PASSED,
            (TestResult("suite::case", "case", "suite", TestStatus.PASSED),),
            0,
            None,
            "[patchground] UNTRUSTED-LOG\nUNTRUSTED-LOG",
        )
        self.files: set[str] = set()
        self.image = ""
        self.command = ""

    def build_image(self, dockerfile: Path, *, name: str) -> BuildResult:
        self.builds += 1
        if self.error:
            raise self.error
        return BuildResult("sha256:frozen", "unused", "UNTRUSTED-LOG")

    def run_check(self, image_id: str, layers: Sequence[Path], command: str) -> RunResult:
        self.runs += 1
        self.image, self.command = image_id, command
        self.files = {p.relative_to(layers[0]).as_posix() for p in layers[0].rglob("*")}
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def sandbox() -> FakeSandbox:
    return FakeSandbox()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "sessions"


@pytest.fixture
def authored(tmp_path: Path) -> Path:
    path = tmp_path / "sample"
    for folder in ("workspace", "checks/visible", "checks/hidden", "environment", "solution"):
        (path / folder).mkdir(parents=True)
    (path / "workspace/code.py").write_text("value = 0\n")
    (path / "checks/visible/visible.py").write_text("# visible fixture\n")
    (path / "checks/hidden/private.py").write_text("# synthetic private fixture\n")
    (path / "solution/reference.patch").write_text("synthetic reference fixture")
    (path / "environment/Dockerfile").write_text("FROM scratch\n")
    (path / "TICKET.md").write_text("[red]Fix the challenge[/red]\n")
    (path / "challenge.yaml").write_text("""spec_version: "0.1"
id: sample
version: 1.0.0
title: Sample
type: debug
summary: A fixture
languages: [python]
difficulty: beginner
timebox_minutes: 20
ai_policy: allowed
environment:
  dockerfile: environment/Dockerfile
  test_command: frozen-command
checks:
  visible: checks/visible
  hidden: checks/hidden
solution: solution/reference.patch
author: {name: Fixture}
""")
    return path
