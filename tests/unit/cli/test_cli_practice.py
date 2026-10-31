import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from patchground.authoring import create_challenge
from patchground.cli.app import app
from patchground.sandbox import BuildResult, CommandResult
from patchground.sessions import start_session

runner = CliRunner()


@pytest.fixture
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    created = create_challenge("practice-fixture")
    manifest = tmp_path / created.path / "challenge.yaml"
    manifest.write_text(manifest.read_text() + "\nhints: [A clue]\n")
    box = Mock()
    box.build_image.return_value = BuildResult("sha256:fixture", "fixture", "")
    return start_session(tmp_path / created.path, sandbox=box).session


def test_hints_sessions_history_are_registered_json(session: Path) -> None:
    hinted = runner.invoke(app, ["hint", "--session", str(session), "--json"])
    assert hinted.exit_code == 0
    assert json.loads(hinted.stdout)["hint"] == "A clue"
    exhausted = runner.invoke(app, ["hint", "--session", str(session), "--json"])
    assert json.loads(exhausted.stdout)["exhausted"] is True
    listed = runner.invoke(app, ["sessions", "--json"])
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)["sessions"][0]["challenge_id"] == "practice-fixture"
    history = runner.invoke(app, ["history", "--session", str(session), "--json"])
    assert history.exit_code == 0
    assert json.loads(history.stdout)["enabled"] is True


def test_start_can_disable_checkpoint_history(session: Path) -> None:
    with patch(
        "patchground.sandbox.build_image", return_value=BuildResult("sha256:fixture", "fixture", "")
    ):
        result = runner.invoke(app, ["start", "practice-fixture", "--no-history", "--json"])
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["history"]["state"] == "disabled"
    history = runner.invoke(app, ["history", "--session", body["session"], "--json"])
    assert json.loads(history.stdout)["availability"] == "disabled"


def test_run_preserves_command_flags_and_json_boundary(session: Path) -> None:
    response = CommandResult(exit_code=0, limit=None, output_tail="command output")
    with patch("patchground.sandbox.run_command", return_value=response) as run:
        result = runner.invoke(
            app, ["run", "--session", str(session), "--json", "--", "echo", "--json"]
        )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["output_tail"] == "command output"
    assert run.call_args.args[2] == ("echo", "--json")
    with patch("patchground.sandbox.run_command", return_value=response):
        human = runner.invoke(app, ["run", "--session", str(session), "--", "echo", "--json"])
    assert human.exit_code == 0
    assert "Command output tail" in human.stdout


def test_run_parse_errors_never_echo_arguments() -> None:
    for arguments in [
        ["run", "--json", "private-argument"],
        ["run", "--private-argument", "--json", "--", "echo"],
        ["run", "--json", "--"],
    ]:
        result = runner.invoke(app, arguments)
        assert result.exit_code == 2
        assert "private-argument" not in result.output
        assert "error" in json.loads(result.stdout)
        assert result.stderr == ""


def test_run_nonzero_is_exit_one(session: Path) -> None:
    response = CommandResult(exit_code=7, limit=None, output_tail="failure")
    with patch("patchground.sandbox.run_command", return_value=response):
        result = runner.invoke(app, ["run", "--session", str(session), "--json", "--", "false"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["exit_code"] == 7
