"""`doctor` rendering and exit contract with mocked probes; registered on a local app."""

from __future__ import annotations

import json

import pytest
import typer
from typer.testing import CliRunner

from patchground.cli import doctor as cli
from patchground.sandbox import EngineProbe, EngineProblem
from patchground.sessions.diagnostics import DiskProbe, DiskProblem, GitProbe, GitProblem

runner = CliRunner()
app = typer.Typer()
app.command("doctor")(cli.doctor)
app.command("unused")(lambda: None)  # keep `doctor` a subcommand


def _probes(monkeypatch: pytest.MonkeyPatch, engine: EngineProbe, git: GitProbe, disk: DiskProbe):
    monkeypatch.setattr(cli, "probe_engine", lambda: engine)
    monkeypatch.setattr(cli, "probe_git", lambda: git)
    monkeypatch.setattr(cli, "probe_disk", lambda: disk)


HEALTHY = (
    EngineProbe(True, engine="Docker", version="27.1.0", api_version="1.46"),
    GitProbe(True, version="2.45.0"),
    DiskProbe(True, "~/patchground/sessions", free_bytes=50 * 1024**3),
)
BROKEN = (
    EngineProbe(False, EngineProblem.NOT_RUNNING),
    GitProbe(False, GitProblem.MISSING),
    DiskProbe(False, "~/patchground/sessions", DiskProblem.LOW_SPACE, free_bytes=1024**2),
)


def test_healthy_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _probes(monkeypatch, *HEALTHY)
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["healthy"] is True
    assert [check["name"] for check in data["checks"]] == ["engine", "git", "disk"]
    assert all(check["status"] == "ok" and check["fix"] is None for check in data["checks"])


def test_every_failure_reported_with_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    _probes(monkeypatch, *BROKEN)
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 2
    data = json.loads(result.stdout)
    assert data["healthy"] is False
    assert [c["problem"] for c in data["checks"]] == ["not_running", "missing", "low_space"]
    assert all(c["status"] == "failed" and c["fix"] for c in data["checks"])


def test_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _probes(monkeypatch, *BROKEN)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 2
    assert result.stdout.count("fix:") == 3
    assert "not ready: 3 check(s) failed" in result.stdout


@pytest.mark.parametrize("platform", ["macos", "linux", "windows"])
@pytest.mark.parametrize("problem", list(EngineProblem))
def test_engine_fix_for_every_problem(platform: str, problem: EngineProblem) -> None:
    check = cli.engine_check(EngineProbe(False, problem), platform)
    assert check.fix and check.problem == problem.value
    if platform == "windows":
        assert "WSL2" in check.fix


@pytest.mark.parametrize("problem", list(DiskProblem))
def test_disk_fix_for_every_problem(problem: DiskProblem) -> None:
    check = cli.disk_check(DiskProbe(False, "~/x", problem, free_bytes=1))
    assert check.fix and "~/x" in check.detail


def test_unexpected_error_is_one_internal_document(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> EngineProbe:
        raise RuntimeError("sk-test-not-a-real-key")

    _probes(monkeypatch, *HEALTHY)
    monkeypatch.setattr(cli, "probe_engine", boom)
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["kind"] == "internal"
    assert "sk-test" not in result.stdout
