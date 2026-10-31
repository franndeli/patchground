"""Session CLI rendering and exit contract, without Docker or logs."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from patchground.cli import sessions as cli
from patchground.cli.app import app
from patchground.sandbox import RunOutcome
from patchground.sessions import CheckResult, SessionError, StartedSession

runner = CliRunner()


@pytest.mark.parametrize("json_mode", [True, False])
def test_start(monkeypatch, json_mode):
    calls = []

    def start(path, *, timer, history):
        calls.append((path, timer, history))
        return StartedSession(
            session=Path("session"),
            workspace=Path("session/workspace"),
            challenge_id="sample",
            timer=timer,
            ticket="[red]literal ticket[/red]",
        )

    monkeypatch.setattr(cli, "start_session", start)
    result = runner.invoke(
        app, ["start", "authored", "--no-timer", *(["--json"] if json_mode else [])]
    )
    assert result.exit_code == 0
    assert calls == [(Path("authored"), False, True)]
    if json_mode:
        assert json.loads(result.stdout)["timer"] is False
    else:
        assert "[red]literal ticket[/red]" in result.stdout


@pytest.mark.parametrize("outcome", list(RunOutcome))
def test_check_nonpassing_and_empty(monkeypatch, outcome):
    def check(session):
        assert session == Path("selected")
        return CheckResult(outcome=outcome, tests=(), duration_seconds=0)

    monkeypatch.setattr(cli, "check_session", check)
    result = runner.invoke(app, ["check", "--session", "selected", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["passed"] is False


@pytest.mark.parametrize(
    "command,api",
    [("start", "start_session"), ("check", "check_session"), ("status", "session_status")],
)
@pytest.mark.parametrize(
    "error,code,kind",
    [
        (SessionError("session busy"), 2, "environment"),
        (RuntimeError("UNTRUSTED-LOG"), 2, "internal"),
        (KeyboardInterrupt(), 130, "interrupted"),
    ],
)
def test_errors_are_one_document(monkeypatch, command, api, error, code, kind):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, api, fail)
    args = [command, *(["authored"] if command == "start" else []), "--json"]
    result = runner.invoke(app, args)
    assert result.exit_code == code
    assert json.loads(result.stdout)["error"]["kind"] == kind
    assert "UNTRUSTED-LOG" not in result.output


def test_no_selection_is_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    for command in ("check", "status"):
        result = runner.invoke(app, [command, "--json"])
        assert result.exit_code == 2
        assert "error" in json.loads(result.stdout)


@pytest.mark.parametrize(
    "args",
    [
        ["start", "--json"],
        ["check", "--not-a-real-option", "--json"],
        ["status", "--json", "--session"],
    ],
)
def test_usage_errors_are_one_document(args):
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["kind"] == "environment"
    assert not result.stderr
