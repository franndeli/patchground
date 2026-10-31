from pathlib import Path
from unittest.mock import patch

import pytest

from patchground.authoring import AuthoringError, create_challenge
from patchground.authoring.create import TEMPLATE_FILES
from patchground.spec import load_challenge


def test_runnable_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = create_challenge("my-challenge")
    root = tmp_path / result.path
    assert result.id == "my-challenge"
    assert set(result.files) == set(TEMPLATE_FILES)
    assert load_challenge(root).manifest.id == result.id
    assert not (root / ".git").exists()
    assert not (root / "verification.json").exists()
    assert {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} == set(TEMPLATE_FILES)


@pytest.mark.parametrize("challenge_id", ["", "../bad", "two/parts", "Bad", "-bad", "bad--id", "."])
def test_invalid_ids_do_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, challenge_id: str
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(AuthoringError, match="id must"):
        create_challenge(challenge_id)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind,language", [("feature", "python"), ("debug", "typescript")])
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
