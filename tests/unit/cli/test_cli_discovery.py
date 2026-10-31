"""`list` / `show` rendering and exit contract, on a local Typer app (registration is elsewhere)."""

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from patchground.cli import discovery as cli
from patchground.cli.discovery import DiscoveryCommand, list_challenges, show

HIDDEN = "SYNTHETIC-HIDDEN-MARKER"
REFERENCE = "SYNTHETIC-REFERENCE-MARKER"


def make_challenge(
    parent: Path,
    name: str,
    *,
    type_: str = "debug",
    difficulty: str = "beginner",
    languages: str = "[python]",
    tags: str = "[pagination]",
) -> Path:
    path = parent / name
    for folder in ("workspace", "checks/visible", "checks/hidden", "environment", "solution"):
        (path / folder).mkdir(parents=True)
    (path / "workspace/code.py").write_text("value = 0\n")
    (path / "checks/visible/test_visible.py").write_text("# visible\n")
    (path / "checks/hidden/test_hidden.py").write_text(f"# {HIDDEN}\n")
    (path / "solution/reference.patch").write_text(REFERENCE)
    (path / "environment/Dockerfile").write_text("FROM scratch\n")
    (path / "TICKET.md").write_text(f"Fix {name}\n")
    (path / "challenge.yaml").write_text(f"""spec_version: "0.1"
id: {name}
version: 1.0.0
title: Title of {name}
type: {type_}
summary: Summary of {name}
languages: {languages}
tags: {tags}
difficulty: {difficulty}
timebox_minutes: 20
ai_policy: allowed
environment:
  dockerfile: environment/Dockerfile
  test_command: run-{HIDDEN}
checks:
  visible: checks/visible
  hidden: checks/hidden
solution: solution/reference.patch
hints: ["{HIDDEN} hint"]
author: {{name: Fixture}}
""")
    return path


app = typer.Typer()
app.command("list", cls=DiscoveryCommand)(list_challenges)
app.command("show", cls=DiscoveryCommand)(show)
runner = CliRunner()


@pytest.mark.parametrize("json_mode", [True, False])
def test_list_empty(tmp_path, json_mode):
    result = runner.invoke(app, ["list", str(tmp_path), *(["--json"] if json_mode else [])])
    assert result.exit_code == 0
    if json_mode:
        data = json.loads(result.stdout)
        assert data["challenges"] == [] and data["invalid"] == []
    else:
        assert "no challenges found" in result.stdout


def test_list_filters_and_json(tmp_path):
    make_challenge(tmp_path, "one")
    make_challenge(tmp_path, "two", type_="feature", tags="[http]")
    result = runner.invoke(app, ["list", str(tmp_path), "--type", "feature", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert [item["id"] for item in data["challenges"]] == ["two"]
    assert data["filters"]["type"] == "feature"
    assert HIDDEN not in result.stdout


def test_list_invalid_exits_one_and_reports(tmp_path):
    make_challenge(tmp_path, "good")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "challenge.yaml").write_text("not: [valid\n")
    (bad / "TICKET.md").write_text("ticket")
    for args in (["--json"], []):
        result = runner.invoke(app, ["list", str(tmp_path), *args])
        assert result.exit_code == 1
        assert "bad" in result.stdout
    data = json.loads(runner.invoke(app, ["list", str(tmp_path), "--json"]).stdout)
    assert [item["id"] for item in data["challenges"]] == ["good"]
    assert data["invalid"][0]["name"] == "bad"


def test_list_missing_directory_is_environment_error(tmp_path):
    result = runner.invoke(app, ["list", str(tmp_path / "missing"), "--json"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["kind"] == "environment"


@pytest.mark.parametrize(
    "args", [["list", "--type", "nope", "--json"], ["show", "--json"], ["list", "--bad", "--json"]]
)
def test_usage_errors_are_one_document(args):
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["kind"] == "environment"


@pytest.mark.parametrize("json_mode", [True, False])
def test_show(tmp_path, json_mode):
    challenge = make_challenge(tmp_path, "alpha")
    (challenge / "TICKET.md").write_text("[red]literal[/red] \x1b[31mesc\n")
    result = runner.invoke(app, ["show", str(challenge), *(["--json"] if json_mode else [])])
    assert result.exit_code == 0
    assert HIDDEN not in result.stdout
    assert REFERENCE not in result.stdout
    if json_mode:
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["challenge"]["id"] == "alpha"
    else:
        assert "[red]literal[/red]" in result.stdout
        assert "\x1b" not in result.stdout


def test_show_invalid_exits_one(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    result = runner.invoke(app, ["show", str(folder), "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["valid"] is False


@pytest.mark.parametrize(
    "error,code,kind",
    [(RuntimeError("UNTRUSTED"), 2, "internal"), (KeyboardInterrupt(), 130, "interrupted")],
)
def test_unexpected_errors_are_one_document(monkeypatch, tmp_path, error, code, kind):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "show_reference", fail)
    result = runner.invoke(app, ["show", str(tmp_path), "--json"])
    assert result.exit_code == code
    assert json.loads(result.stdout)["error"]["kind"] == kind
    assert "UNTRUSTED" not in result.output
