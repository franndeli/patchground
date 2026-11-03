"""Keep the standalone guide and public entry points consistent with the CLI."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from patchground.cli.app import app

ROOT = Path(__file__).resolve().parents[2]
SKILL = Path("skills/patchground/SKILL.md")
REPO = "https://github.com/franndeli/patchground/blob/main/"


def assert_public_guidance(root: Path) -> None:
    skill = (root / SKILL).read_text()
    parts = skill.split("---", 2)
    assert len(parts) == 3 and not parts[0].strip(), "skill needs YAML frontmatter"
    metadata = YAML(typ="safe").load(parts[1])
    assert metadata["name"] == SKILL.parent.name
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", metadata["name"])
    assert len(metadata["name"]) <= 64
    assert isinstance(metadata["description"], str) and 0 < len(metadata["description"]) <= 1024
    for link in re.findall(r"\]\(([^)]+)\)", skill):
        assert link.startswith(REPO), f"standalone guide needs public documentation: {link}"
        assert (root / link.removeprefix(REPO).split("#")[0]).is_file(), link

    readme = (root / "README.md").read_text()
    assert f"]({REPO}{SKILL.as_posix()})" in readme
    assert "## Use your AI assistant as a guide" in readme
    assert "--type debug|feature" in readme
    assert "--lang python|typescript" in readme
    assert "Only that template combination is currently supported" not in readme
    first_session = (root / "docs/first-session.md").read_text()
    assert "accept challenge paths, not IDs" not in first_session
    assert "list --builtin" in first_session

    install = (root / "web/src/components/Install.astro").read_text()
    assert f"/blob/main/{SKILL.as_posix()}" in install
    assert "README.md#use-your-ai-assistant-as-a-guide" in install


def test_standalone_guide_and_public_docs() -> None:
    assert_public_guidance(ROOT)


@pytest.mark.parametrize(
    ("path", "old", "new", "message"),
    [
        (SKILL, "name: patchground", "name: wrong-name", None),
        (
            SKILL,
            "docs/first-session.md",
            "docs/missing-guide.md",
            "missing-guide",
        ),
        (
            Path("README.md"),
            "Choose `--type debug|feature` and `--lang python|typescript` "
            "for any of the four starters.",
            "Only that template combination is currently supported.",
            None,
        ),
        (
            Path("docs/first-session.md"),
            "accept built-in IDs, installed references, and local paths",
            "accept challenge paths, not IDs",
            None,
        ),
    ],
)
def test_guidance_check_rejects_broken_fixture(
    tmp_path: Path, path: Path, old: str, new: str, message: str | None
) -> None:
    sources = [SKILL, Path("README.md"), Path("docs"), Path("web/src/components/Install.astro")]
    for source in sources:
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        if (ROOT / source).is_dir():
            shutil.copytree(ROOT / source, target)
        else:
            shutil.copyfile(ROOT / source, target)
    original = (tmp_path / path).read_text()
    assert old in original, "the fixture must actually introduce the intended defect"
    (tmp_path / path).write_text(original.replace(old, new))
    with pytest.raises(AssertionError, match=message):
        assert_public_guidance(tmp_path)


@pytest.mark.parametrize("language", ["python", "typescript"])
@pytest.mark.parametrize("type_", ["debug", "feature"])
def test_documented_starters_create_outside_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str, type_: str
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app, ["new", "guide-demo", "--lang", language, "--type", type_, "--json"]
    )
    assert result.exit_code == 0, result.stdout
    created = json.loads(result.stdout)
    assert created["language"] == language and created["type"] == type_
    assert (tmp_path / "guide-demo/challenge.yaml").is_file()
    repeated = runner.invoke(app, ["new", "guide-demo", "--json"])
    assert repeated.exit_code == 2


def test_documented_skill_install_refuses_existing_destination(tmp_path: Path) -> None:
    readme = (ROOT / "README.md").read_text()
    section = readme.split("## Use your AI assistant as a guide", 1)[1].split("\n## ", 1)[0]
    commands = re.search(r"```sh\n(.*?)```", section, re.DOTALL).group(1)
    env = {**os.environ, "HOME": str(tmp_path)}
    installed = subprocess.run(
        ["sh", "-eu", "-c", commands], cwd=ROOT, env=env, capture_output=True, check=False
    )
    assert installed.returncode == 0
    skill = tmp_path / ".agents/skills/patchground/SKILL.md"
    assert skill.read_bytes() == (ROOT / SKILL).read_bytes()
    skill.write_text("existing local customization\n")
    repeated = subprocess.run(
        ["sh", "-eu", "-c", commands], cwd=ROOT, env=env, capture_output=True, check=False
    )
    assert repeated.returncode != 0
    assert skill.read_text() == "existing local customization\n"


def test_documented_builtin_id_resolves_outside_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    listed = runner.invoke(app, ["list", "--builtin", "--json"])
    assert listed.exit_code == 0
    assert "pagination-last-page" in listed.stdout
    shown = runner.invoke(app, ["show", "pagination-last-page", "--json"])
    assert shown.exit_code == 0
    assert "pagination-last-page" in shown.stdout
    assert not list(tmp_path.iterdir()), "discovery must not create a workspace or local catalog"
