"""The curated catalog shipped with the CLI: discovery, resolution precedence and no writes."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from patchground.cli.app import app
from patchground.packs import builtin
from patchground.packs.builtin import builtin_challenge, builtin_root, is_builtin_path
from patchground.packs.execution import resolve_challenge

REPO = Path(__file__).resolve().parents[3]
CURATED = sorted(
    path.name for path in (REPO / "examples").iterdir() if (path / "challenge.yaml").is_file()
)


def test_source_checkout_uses_examples_as_catalog() -> None:
    assert builtin_root() == REPO / "examples"
    assert builtin_challenge("pagination-last-page") == REPO / "examples/pagination-last-page"
    assert builtin_challenge("no-such-challenge") is None
    assert builtin_challenge("../examples") is None
    assert is_builtin_path(REPO / "examples/cache-expiry/workspace")
    assert not is_builtin_path(REPO / "src")


def test_bare_id_falls_back_to_builtin_after_local_and_installed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    resolved = resolve_challenge("pagination-last-page", root=tmp_path / "state")
    assert resolved.pack is None
    assert resolved.path == REPO / "examples/pagination-last-page"
    # An existing local folder of the same name keeps its local meaning.
    (tmp_path / "pagination-last-page").mkdir()
    local = resolve_challenge("pagination-last-page", root=tmp_path / "state")
    assert local.path == Path("pagination-last-page")


def test_list_builtin_and_empty_hint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    listed = runner.invoke(app, ["list", "--builtin", "--json"])
    assert listed.exit_code == 0
    assert sorted(item["id"] for item in json.loads(listed.stdout)["challenges"]) == CURATED
    empty = runner.invoke(app, ["list"])
    assert empty.exit_code == 0
    assert "pgnd list --builtin" in empty.stdout
    assert "pgnd new" in empty.stdout
    assert json.loads(runner.invoke(app, ["list", "--json"]).stdout)["challenges"] == []
    conflict = runner.invoke(app, ["list", "--builtin", "--installed", "--json"])
    assert conflict.exit_code == 2


def test_list_builtin_without_catalog_is_an_environment_error(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtin, "builtin_root", lambda: None)
    monkeypatch.setattr("patchground.cli.discovery.builtin_root", lambda: None)
    result = CliRunner().invoke(app, ["list", "--builtin", "--json"])
    assert result.exit_code == 2
    assert "no built-in challenges" in result.stdout


@pytest.mark.parametrize("reference", ["pagination-last-page"])
def test_validate_never_writes_into_the_catalog(reference, monkeypatch) -> None:
    seen: dict[str, bool] = {}

    def fake_validate(path, *, write, **_kwargs):
        seen["write"] = write
        raise KeyboardInterrupt

    monkeypatch.setattr("patchground.cli.validate.validate_challenge", fake_validate)
    result = CliRunner().invoke(app, ["validate", reference, "--json"])
    assert result.exit_code != 0
    assert seen == {"write": False}
