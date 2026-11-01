import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from patchground.cli.app import app

runner = CliRunner()


def test_new_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "new-one", "--json"])
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["id"] == body["path"] == "new-one"
    assert body["type"] == "debug"
    assert body["language"] == "python"
    assert len(body["files"]) == 8
    assert result.stderr == ""


def test_new_human(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "new-one"])
    assert result.exit_code == 0
    assert "pgnd validate new-one" in result.stdout


def test_new_errors_are_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    for arguments in [[], ["bad--id"], ["valid", "--lang", "rust"], ["valid", "--unknown"]]:
        result = runner.invoke(app, ["new", *arguments, "--json"])
        assert result.exit_code == 2
        assert "error" in json.loads(result.stdout)
        assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_new_does_not_build_or_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with patch("subprocess.Popen", side_effect=AssertionError("must not execute")):
        result = runner.invoke(app, ["new", "new-one"])
    assert result.exit_code == 0


def test_new_hides_unexpected_exception_detail() -> None:
    with patch(
        "patchground.cli.authoring.create_challenge", side_effect=RuntimeError("private-detail")
    ):
        result = runner.invoke(app, ["new", "new-one", "--json"])
    assert result.exit_code == 2
    assert "private-detail" not in result.output
    assert json.loads(result.stdout)["error"]["kind"] == "internal"


def test_new_feature_python_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["new", "new-one", "--type", "feature", "--lang", "python", "--json"]
    )
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert (body["type"], body["language"]) == ("feature", "python")
    assert len(body["files"]) == 8


def test_new_typescript_reports_selected_starter(tmp_path: Path, monkeypatch) -> None:
    from patchground import runner_assets

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_assets, "vitest_assets", lambda: {"Dockerfile": b"x"}, raising=False)
    result = runner.invoke(
        app, ["new", "new-one", "--type", "debug", "--lang", "typescript", "--json"]
    )
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert (body["type"], body["language"]) == ("debug", "typescript")
    assert "environment/Dockerfile" in body["files"]
    assert "private" not in result.output


def test_new_unsupported_combination_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["new", "new-one", "--type", "review", "--lang", "typescript", "--json"]
    )
    assert result.exit_code == 2
    assert "supported templates" in json.loads(result.stdout)["error"]["message"]
    assert list(tmp_path.iterdir()) == []
