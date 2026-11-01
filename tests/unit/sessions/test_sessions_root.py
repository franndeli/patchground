"""`PATCHGROUND_SESSIONS_DIR` selects where sessions live; relative values are refused."""

from pathlib import Path

import pytest

from patchground.sessions import store
from patchground.sessions.diagnostics import DiskProblem, probe_disk
from patchground.sessions.models import SessionError


def test_default_root_is_under_home(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(store.SESSIONS_ENV, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert store.default_root() == tmp_path / "patchground" / "sessions"


def test_absolute_override_is_used(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(store.SESSIONS_ENV, str(tmp_path / "practice"))
    assert store.default_root() == (tmp_path / "practice").resolve()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(store.SESSIONS_ENV, "~/elsewhere")
    assert store.default_root() == (Path(tmp_path) / "elsewhere").resolve()


def test_relative_override_is_refused(monkeypatch) -> None:
    monkeypatch.setenv(store.SESSIONS_ENV, "relative/sessions")
    with pytest.raises(SessionError, match="absolute"):
        store.default_root()
    probe = probe_disk()
    assert not probe.ok and probe.problem is DiskProblem.INVALID_SETTING


def test_sessions_created_under_override(authored, sandbox, monkeypatch, tmp_path) -> None:
    from patchground.sessions import start_session

    target = tmp_path / "chosen"
    monkeypatch.setenv(store.SESSIONS_ENV, str(target))
    started = start_session(authored, sandbox=sandbox)
    assert started.session.parent == target.resolve()
