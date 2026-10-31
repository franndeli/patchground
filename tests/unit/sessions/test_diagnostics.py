"""Git and disk probes: bounded, read-only, display-safe paths."""

from __future__ import annotations

import subprocess
from collections import namedtuple
from pathlib import Path

import pytest

from patchground.sessions import diagnostics
from patchground.sessions.diagnostics import DiskProblem, GitProblem, probe_disk, probe_git

Usage = namedtuple("Usage", "total used free")


def test_git_available() -> None:
    probe = probe_git()
    assert probe.available and probe.version


def test_git_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: None)
    assert probe_git().problem is GitProblem.MISSING


def test_git_timeout_is_unusable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "git"
    fake.write_text("")
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: str(fake))

    def run(*args: object, **kwargs: object) -> None:
        assert kwargs["timeout"] == diagnostics._GIT_TIMEOUT
        env = kwargs["env"]
        assert isinstance(env, dict) and env["GIT_CONFIG_GLOBAL"]
        raise subprocess.TimeoutExpired("git", 10)

    monkeypatch.setattr(diagnostics.subprocess, "run", run)
    assert probe_git().problem is GitProblem.UNUSABLE


def test_git_unrecognised_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "git"
    fake.write_text("")
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: str(fake))
    monkeypatch.setattr(
        diagnostics.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=b"nope", stderr=b""),
    )
    assert probe_git().problem is GitProblem.UNUSABLE


def test_disk_ok_on_missing_root_without_creating_it(tmp_path: Path) -> None:
    root = tmp_path / "a" / "b"
    probe = probe_disk(root, minimum_bytes=1)
    assert probe.ok and probe.free_bytes and probe.minimum_bytes == 1
    assert not (tmp_path / "a").exists()


def test_disk_low_space(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(diagnostics.shutil, "disk_usage", lambda _p: Usage(10, 9, 1))
    probe = probe_disk(tmp_path)
    assert probe.problem is DiskProblem.LOW_SPACE and probe.free_bytes == 1
    assert probe.minimum_bytes == 1024**3


def test_disk_blocked_by_file(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("")
    assert probe_disk(tmp_path / "file" / "sessions").problem is DiskProblem.NOT_WRITABLE


def test_disk_not_writable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(diagnostics.os, "access", lambda *_a: False)
    assert probe_disk(tmp_path).problem is DiskProblem.NOT_WRITABLE


def test_disk_usage_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail(_path: object) -> None:
        raise OSError("boom")

    monkeypatch.setattr(diagnostics.shutil, "disk_usage", fail)
    assert probe_disk(tmp_path).problem is DiskProblem.UNREADABLE


def test_display_path_hides_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(diagnostics.Path, "home", classmethod(lambda cls: tmp_path))
    assert diagnostics.display_path(tmp_path / "patchground" / "sessions") == (
        "~/patchground/sessions"
    )
    assert diagnostics.display_path(tmp_path) == "~"
    assert probe_disk(tmp_path / "x").location == "~/x"
