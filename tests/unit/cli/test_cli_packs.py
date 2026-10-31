import json
from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from patchground.cli.app import app
from patchground.packs.registry import add_pack, list_packs
from patchground.sandbox import BuildResult
from patchground.sessions import start_session

runner = CliRunner()


def invoke(*args: str, expected: int = 0):
    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code == expected, result.stdout
    assert result.stderr == ""
    return json.loads(result.stdout)


def test_pack_cli_install_discover_consent_and_remove(pack_repo) -> None:
    source, _git = pack_repo
    installed = invoke("pack", "add", str(source))
    assert installed["pack"]["trust"] == "unofficial" and not installed["consented"]
    assert len(invoke("pack", "list")["packs"]) == 1
    indexed = invoke("list", "--installed")
    assert indexed["challenges"][0]["reference"] == "sample-pack:pack-exercise"
    assert invoke("show", "sample-pack:pack-exercise")["valid"]
    with patch("patchground.sandbox.build_image") as build:
        required = invoke("start", "sample-pack:pack-exercise", expected=2)
        assert required["error"]["kind"] == "consent_required"
        assert len(required["review"]["recipes"]) == 1
        invoke("validate", str(Path(installed["path"]) / "pack-exercise"), expected=2)
        build.assert_not_called()
    invoke("pack", "remove", "sample-pack", expected=2)
    assert len(list_packs().packs) == 1
    removed = invoke("pack", "remove", "sample-pack", "--yes")
    assert removed["removed_versions"] == 1
    assert invoke("pack", "list")["packs"] == []


def test_start_approval_freezes_pack_provenance(pack_repo) -> None:
    source, git = pack_repo
    add_pack(source)
    box = Mock()
    box.build_image.return_value = BuildResult("sha256:fixture", "fixture", "")
    with (
        patch("patchground.cli.sessions.start_session", wraps=start_session),
        patch("patchground.sandbox.build_image", side_effect=box.build_image),
    ):
        started = invoke("start", "sample-pack:pack-exercise", "--yes", "--no-history")
    record = json.loads((Path(started["session"]) / ".session/session.json").read_text())
    assert record["trust"] == "unofficial"
    assert record["pack"]["commit"] == git("rev-parse", "HEAD")
    assert record["source"] != str(source)
    assert started["pack"]["commit"] == record["pack"]["commit"]
    assert list_packs().packs[0].consented


def test_update_requires_new_approval_and_keeps_previous_revision(pack_repo) -> None:
    source, git = pack_repo
    old = add_pack(source)
    ticket = source / "pack-exercise/TICKET.md"
    ticket.write_text(ticket.read_text() + "\nA revised ticket.\n")
    git("add", "--all")
    git("commit", "-m", "Revise test ticket")
    review = invoke("pack", "update", "sample-pack", expected=2)
    assert review["review"]["previous_commit"] == old.pack.commit
    assert review["review"]["changed"] == ["pack-exercise"]
    assert next(p for p in list_packs().packs if p.active).pack.commit == old.pack.commit
    updated = invoke("pack", "update", "sample-pack", "--yes")
    assert updated["changed"] and updated["current"]["consented"]
    assert len(list_packs().packs) == 2


def test_interactive_consent_denial_does_not_build(pack_repo) -> None:
    source, _git = pack_repo
    add_pack(source)
    with patch("patchground.sandbox.build_image") as build:
        result = runner.invoke(app, ["start", "sample-pack:pack-exercise"], input="n\n")
    assert result.exit_code == 130
    assert "UNOFFICIAL" in result.stdout and "Dockerfile:" in result.stdout
    assert "test_starter_hidden.py" not in result.stdout
    assert not list_packs().packs[0].consented
    build.assert_not_called()


def test_json_escapes_terminal_controls() -> None:
    from io import StringIO

    from patchground.cli.render import emit

    output = StringIO()
    with patch("sys.stdout", output):
        emit({"text": "\u009b31m"}, lambda _console: None, True)
    assert "\u009b" not in output.getvalue()
    assert json.loads(output.getvalue())["text"] == "\u009b31m"


def test_management_errors_never_echo_mistaken_credential_urls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    mistaken = "https://user:fake-password@example.test/repo"
    for action in ("update", "remove"):
        result = invoke("pack", action, mistaken, "--yes", expected=2)
        assert mistaken not in json.dumps(result)
        assert "fake-password" not in json.dumps(result)
