import re
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from patchground import runner_assets
from patchground.authoring import AuthoringError, create_challenge
from patchground.authoring.create import TEMPLATE_FILES
from patchground.spec import load_challenge

FAKE_ASSETS = {
    "Dockerfile": b"FROM scratch\n",
    "vitest-runner.mjs": b"// fake\n",
    "lock/a.json": b"{}",
}
COMBINATIONS = [
    ("debug", "python"),
    ("feature", "python"),
    ("debug", "typescript"),
    ("feature", "typescript"),
]


@pytest.fixture
def fake_assets(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    assets = dict(FAKE_ASSETS)
    monkeypatch.setattr(runner_assets, "vitest_assets", lambda: assets, raising=False)
    return assets


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_runnable_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = create_challenge("my-challenge")
    root = tmp_path / result.path
    assert result.id == "my-challenge"
    assert set(result.files) == set(TEMPLATE_FILES)
    assert load_challenge(root).manifest.id == result.id
    assert not (root / ".git").exists()
    assert not (root / "verification.json").exists()
    assert _files(root) == set(TEMPLATE_FILES)


@pytest.mark.parametrize("challenge_id", ["", "../bad", "two/parts", "Bad", "-bad", "bad--id", "."])
def test_invalid_ids_do_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, challenge_id: str
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(AuthoringError, match="id must"):
        create_challenge(challenge_id)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("fake_assets")
@pytest.mark.parametrize(("kind", "language"), COMBINATIONS)
def test_every_combination_is_runnable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, language: str
) -> None:
    monkeypatch.chdir(tmp_path)
    result = create_challenge("new-one", type_=kind, language=language)
    root = tmp_path / "new-one"
    manifest = load_challenge(root).manifest
    assert (result.type, result.language) == (kind, language)
    assert (manifest.type.value, manifest.languages) == (kind, [language])
    assert manifest.id == "new-one"
    assert set(result.files) == _files(root)
    assert not (root / ".git").exists()
    if language == "typescript":
        assert manifest.environment.test_command == runner_assets.VITEST_COMMAND
        for name, content in FAKE_ASSETS.items():
            assert (root / "environment" / name).read_bytes() == content
        assert {f"environment/{n}" for n in FAKE_ASSETS} <= set(result.files)
    else:
        assert "environment/vitest-runner.mjs" not in result.files


def test_python_debug_remains_default_and_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = create_challenge("new-one")
    assert (result.type, result.language, result.files) == ("debug", "python", TEMPLATE_FILES)


@pytest.mark.usefixtures("fake_assets")
@pytest.mark.parametrize(("kind", "language"), COMBINATIONS)
def test_reference_patch_changes_only_the_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, language: str
) -> None:
    monkeypatch.chdir(tmp_path)
    create_challenge("new-one", type_=kind, language=language)
    root = tmp_path / "new-one"
    patch_text = (root / "solution/reference.patch").read_text()
    touched = re.findall(r"^diff --git a/(\S+)", patch_text, re.MULTILINE)
    assert touched == ["src/starter.ts" if language == "typescript" else "src/starter.py"]
    workspace = tmp_path / "copy"
    shutil.copytree(root / "workspace", workspace)
    subprocess.run(
        ["git", "apply", "--check", str(root / "solution/reference.patch")],
        cwd=workspace,
        check=True,
        capture_output=True,
    )


@pytest.mark.usefixtures("fake_assets")
@pytest.mark.parametrize("kind", ["debug", "feature"])
def test_typescript_checks_use_the_supported_subset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.chdir(tmp_path)
    create_challenge("new-one", type_=kind, language="typescript")
    root = tmp_path / "new-one"
    names: list[str] = []
    for check in sorted(root.glob("checks/*/tests/*")):
        assert check.name.endswith(".test.ts")
        text = check.read_text()
        assert re.search(r'^import \{[^}]*\} from "vitest";$', text, re.MULTILINE)
        assert not re.search(
            r"describe|beforeEach|afterEach|beforeAll|afterAll|\.skip|\.only", text
        )
        names += re.findall(r'^test\("([^"]+)", \(\) => \{$', text, re.MULTILINE)
        assert len(re.findall(r"^test\(", text, re.MULTILINE)) == len(
            re.findall(r'^test\("', text, re.MULTILINE)
        )
    assert len(names) == len(set(names)) >= 4


@pytest.mark.parametrize(
    "assets",
    [
        {"vitest-runner.mjs": b"x"},
        {"Dockerfile": b"x", "../escape": b"x"},
        {"Dockerfile": b"x", "/abs": b"x"},
        {"Dockerfile": b"x", "a": b"x", "a/b": b"x"},
        {"Dockerfile": b"x", "dir\\file": b"x"},
        {"Dockerfile": b"x", "text": "not bytes"},
    ],
)
def test_incomplete_or_unsafe_runner_assets_fail_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, assets: dict[str, object]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner_assets, "vitest_assets", lambda: assets, raising=False)
    with pytest.raises(AuthoringError, match="runner assets"):
        create_challenge("new-one", type_="debug", language="typescript")
    assert list(tmp_path.iterdir()) == []


def test_unavailable_runner_assets_fail_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def broken() -> dict[str, bytes]:
        raise OSError("missing resource")

    monkeypatch.setattr(runner_assets, "vitest_assets", broken, raising=False)
    with pytest.raises(AuthoringError, match="runner assets are unavailable"):
        create_challenge("new-one", type_="feature", language="typescript")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("fake_assets")
def test_typescript_rollback_removes_runner_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with (
        patch("patchground.authoring.create.os.fsync", side_effect=OSError("disk full")),
        pytest.raises(AuthoringError, match="could not create"),
    ):
        create_challenge("new-one", type_="debug", language="typescript")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("kind", "language"),
    [("review", "python"), ("refactor", "typescript"), ("debug", "go"), ("feature", "rust")],
)
def test_unsupported_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, language: str
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(AuthoringError, match="supported template"):
        create_challenge("new-one", type_=kind, language=language)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("existing", ["file", "directory", "symlink", "dangling"])
def test_never_overwrites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing: str) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "new-one"
    if existing == "file":
        target.write_text("keep")
    elif existing == "directory":
        target.mkdir()
        (target / "keep").write_text("keep")
    else:
        outside = tmp_path / "outside"
        if existing == "symlink":
            outside.mkdir()
            (outside / "keep").write_text("keep")
        target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(AuthoringError, match="already exists"):
        create_challenge("new-one")
    assert target.is_symlink() or target.exists()
    if existing == "file":
        assert target.read_text() == "keep"
    elif existing != "dangling":
        assert (target / "keep").read_text() == "keep"
        assert not (target / "challenge.yaml").exists()


def test_write_failure_rolls_back_only_created_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "keep").write_text("unrelated")
    with (
        patch("patchground.authoring.create.os.fsync", side_effect=OSError("disk full")),
        pytest.raises(AuthoringError, match="could not create"),
    ):
        create_challenge("new-one")
    assert [p.name for p in tmp_path.iterdir()] == ["keep"]


def test_rollback_preserves_an_unrelated_added_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def fail(_fd: int) -> None:
        (tmp_path / "new-one" / "keep").write_text("concurrent addition")
        raise OSError("disk full")

    with (
        patch("patchground.authoring.create.os.fsync", side_effect=fail),
        pytest.raises(AuthoringError),
    ):
        create_challenge("new-one")
    assert [p.name for p in (tmp_path / "new-one").iterdir()] == ["keep"]


def test_rollback_does_not_remove_a_replacement_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def fail(_fd: int) -> None:
        manifest = tmp_path / "new-one" / "challenge.yaml"
        manifest.rename(manifest.with_suffix(".original"))
        manifest.write_text("replacement")
        raise OSError("interrupted write")

    with (
        patch("patchground.authoring.create.os.fsync", side_effect=fail),
        pytest.raises(AuthoringError),
    ):
        create_challenge("new-one")
    assert (tmp_path / "new-one" / "challenge.yaml").read_text() == "replacement"


def test_interrupt_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with (
        patch("patchground.authoring.create.os.fsync", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        create_challenge("new-one")
    assert list(tmp_path.iterdir()) == []
