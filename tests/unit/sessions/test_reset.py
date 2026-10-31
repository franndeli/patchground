"""Reset safety and preservation of user-owned Git state."""

import fcntl
import os
import subprocess

import pytest

from patchground.sessions import SessionError, reset_session, session_status, start_session

from .test_workflow import git, state


def test_restore_preserves_git_credentials_timer_and_history(authored, root, sandbox, monkeypatch):
    started = start_session(authored, root=root, sandbox=sandbox)
    work = started.workspace
    (work / "code.py").write_text("staged\n")
    git(work, "add", "code.py")
    before_git = state(work / ".git")
    (work / "code.py").write_text("unstaged\n")
    (work / "visible.py").unlink()
    (work / "extra.py").write_text("remove me")
    (work / "nested").mkdir()
    (work / "nested/.env.local").write_text("fake-sensitive-fixture")
    (work / "nested/ordinary").write_text("remove me too")
    record = (started.session / ".session/session.json").read_bytes()
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("Git invoked"))
    result = reset_session(work, root=root)
    assert result.workspace == work
    assert (work / "code.py").read_text() == "value = 0\n"
    assert (work / "code.py").stat().st_mode & 0o200
    assert (work / "visible.py").exists()
    assert not (work / "extra.py").exists()
    assert not (work / "nested/ordinary").exists()
    assert (work / "nested/.env.local").read_text() == "fake-sensitive-fixture"
    assert state(work / ".git") == before_git
    assert (started.session / ".session/session.json").read_bytes() == record
    assert '"type":"reset"' in (started.session / ".session/events.jsonl").read_text()
    assert session_status(work, root=root).last_check is None
    assert sandbox.runs == 0


@pytest.mark.parametrize("kind", ["symlink", "fifo", "protected_collision"])
def test_rejects_unsafe_tree_before_mutation(authored, root, sandbox, tmp_path, kind):
    started = start_session(authored, root=root, sandbox=sandbox)
    work = started.workspace
    (work / "visible.py").write_text("keep edits")
    if kind == "symlink":
        (work / "unsafe").symlink_to(tmp_path)
    elif kind == "fifo":
        os.mkfifo(work / "unsafe")
    else:
        (work / "code.py").unlink()
        (work / "code.py").mkdir()
        (work / "code.py/.env").write_text("fake-sensitive-fixture")
    with pytest.raises(SessionError):
        reset_session(work, root=root)
    assert (work / "visible.py").read_text() == "keep edits"


def test_hardlink_to_git_index_never_truncated(authored, root, sandbox):
    started = start_session(authored, root=root, sandbox=sandbox)
    index = started.workspace / ".git/index"
    before = index.read_bytes()
    code = started.workspace / "code.py"
    code.unlink()
    code.hardlink_to(index)
    reset_session(started.workspace, root=root)
    assert index.read_bytes() == before
    assert code.read_text() == "value = 0\n"


def test_reset_shares_check_lock(authored, root, sandbox):
    started = start_session(authored, root=root, sandbox=sandbox)
    with (started.session / ".session/lock").open("r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(SessionError, match="session busy"):
            reset_session(started.workspace, root=root)


def test_reset_failure_is_honestly_partial(authored, root, sandbox, monkeypatch):
    started = start_session(authored, root=root, sandbox=sandbox)

    def fail(*args):
        raise OSError("synthetic failure")

    monkeypatch.setattr("patchground.sessions.reset._restore", fail)
    with pytest.raises(SessionError, match="partially restored"):
        reset_session(started.workspace, root=root)
    assert '"type":"reset"' not in (started.session / ".session/events.jsonl").read_text()
