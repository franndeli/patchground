"""Real checks record private checkpoints while preserving all learner Git bytes."""

import os
import shutil
import zlib
from pathlib import Path

import pytest

from patchground.sessions import check_session, history_for_session, start_session

pytestmark = pytest.mark.docker


def test_checkpoint_history_with_real_checks(tmp_path: Path, monkeypatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    example = Path(__file__).resolve().parents[2] / "examples/pagination-last-page"
    source = tmp_path / example.name
    shutil.copytree(example, source, ignore=shutil.ignore_patterns("solution", "verification.json"))
    (source / "solution").mkdir()
    (source / "solution/reference.patch").touch()
    root = tmp_path / "sessions"
    started = start_session(source, root=root)
    (home / ".gitconfig").write_text(f"[core]\n excludesFile = {home / 'ignore'}\n")
    (home / "ignore").write_text("global-private.txt\n")
    info = started.workspace / ".git/info"
    info.mkdir()
    (info / "exclude").write_text("info-private.txt\n")
    for name in ("global-private.txt", "info-private.txt"):
        (started.workspace / name).write_text("private-payload:" + name)
    before = {
        path.relative_to(started.workspace).as_posix(): path.read_bytes()
        for path in (started.workspace / ".git").rglob("*")
        if path.is_file()
    }
    broken = check_session(started.session, root=root)
    assert not broken.passed and broken.history.state == "recorded"
    code = started.workspace / "src/catalog/pagination.py"
    original = code.read_text()
    broken_expression = "max(1, len(items) // per_page)"
    assert broken_expression in original
    code.write_text(
        original.replace(broken_expression, "max(1, (len(items) + per_page - 1) // per_page)")
    )
    fixed = check_session(started.session, root=root)
    assert fixed.passed and fixed.history.state == "recorded"
    saved = history_for_session(started.session, root=root)
    assert saved.availability == "available"
    assert [entry.kind for entry in saved.snapshots] == ["initial", "check", "check"]
    assert [entry.check_outcome for entry in saved.snapshots] == [None, "failed", "passed"]
    assert before == {
        path.relative_to(started.workspace).as_posix(): path.read_bytes()
        for path in (started.workspace / ".git").rglob("*")
        if path.is_file()
    }

    objects = [
        zlib.decompress(path.read_bytes())
        for path in (started.session / ".session/history.git/objects").glob("*/*")
    ]
    assert all(b"private-payload:" not in data for data in objects)
