"""Lifecycle, frozen inputs, safe Git initialization and no workspace Git writes."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from patchground.sandbox import RunOutcome, RunResult, SandboxError, TestResult, TestStatus
from patchground.sessions import SessionError, check_session, session_status, start_session


def git(workspace: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(workspace), *args], check=True, capture_output=True
    ).stdout


def state(path: Path) -> dict[str, bytes]:
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def test_start_layout_baseline_and_source_untouched(authored, root, sandbox):
    before = state(authored)
    result = start_session(authored, root=root, sandbox=sandbox, timer=False)
    assert sandbox.builds == 1 and sandbox.runs == 0
    assert state(authored) == before
    assert set(state(result.workspace)) >= {"code.py", "visible.py"}
    assert set(state(result.session / ".session/original")) == {"code.py", "visible.py"}
    assert "private.py" not in state(result.workspace)
    assert not list(result.session.rglob("reference.patch"))
    assert git(result.workspace, "rev-list", "--count", "HEAD").strip() == b"1"
    assert git(result.workspace, "status", "--porcelain") == b""
    assert (
        git(result.workspace, "log", "-1", "--format=%ae")
        .strip()
        .endswith(b"@users.noreply.github.com")
    )
    assert stat.S_IMODE(result.session.stat().st_mode) == 0o700
    assert not (result.session / ".session/original/code.py").stat().st_mode & 0o222
    status = session_status(result.session, root=root)
    assert not status.timer and status.elapsed_seconds == 0 and status.last_check is None


def test_collision_and_failed_build_rollback(authored, root, sandbox):
    first = start_session(authored, root=root, sandbox=sandbox)
    sandbox.error = SandboxError("UNTRUSTED-LOG")
    with pytest.raises(SessionError, match="could not start"):
        start_session(authored, root=root, sandbox=sandbox)
    assert list(root.iterdir()) == [first.session]
    sandbox.error = None
    second = start_session(authored, root=root, sandbox=sandbox)
    assert second.session.name == first.session.name + "-1"
    assert first.session.exists()


@pytest.mark.parametrize("invalid", ["manifest", "services", "git", "symlink"])
def test_rejected_before_build(authored, root, sandbox, invalid):
    manifest = authored / "challenge.yaml"
    if invalid == "manifest":
        manifest.write_text("not: a-manifest")
    elif invalid == "services":
        manifest.write_text(
            manifest.read_text().replace("  test_command:", "  services: [db]\n  test_command:")
        )
    elif invalid == "git":
        (authored / "workspace/.git").mkdir()
    else:
        (authored / "workspace/link").symlink_to(authored / "TICKET.md")
    with pytest.raises(SessionError):
        start_session(authored, root=root, sandbox=sandbox)
    assert sandbox.builds == 0
    assert not root.exists()


def test_initialization_failure_rolls_back_readonly_original(authored, root, sandbox, monkeypatch):
    def fail(_workspace):
        raise SessionError("git unavailable")

    monkeypatch.setattr("patchground.sessions.git.initialize", fail)
    with pytest.raises(SessionError, match="git unavailable"):
        start_session(authored, root=root, sandbox=sandbox)
    assert not list(root.iterdir())
    assert sandbox.builds == 0


def test_frozen_inputs_and_git_state(authored, root, sandbox, monkeypatch):
    result = start_session(authored, root=root, sandbox=sandbox)
    (result.workspace / "code.py").write_text("staged = True\n")
    git(result.workspace, "add", "code.py")
    (result.workspace / "code.py").write_text("unstaged = True\n")
    (result.workspace / "untracked.py").write_text("new = True\n")
    (result.workspace / ".env.local").write_text("fake-sensitive-fixture")
    (result.workspace / "nested/.git").mkdir(parents=True)
    (result.workspace / "nested/.git/config").write_text("not code")
    before = state(result.workspace)
    manifest = authored / "challenge.yaml"
    manifest.write_text(manifest.read_text().replace("frozen-command", "changed-command"))
    shutil.rmtree(authored)
    # Any Git invocation during check/status is a bug, even a read-only one.
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: pytest.fail("Git invoked after handoff")
    )
    checked = check_session(result.workspace, root=root, sandbox=sandbox)
    assert checked.passed
    assert sandbox.command == "frozen-command" and sandbox.image == "sha256:frozen"
    assert {"code.py", "visible.py", "private.py", "untracked.py"} <= sandbox.files
    assert not any(".git" in part or ".env" in part for part in sandbox.files)
    assert state(result.workspace) == before
    assert "UNTRUSTED-LOG" not in checked.model_dump_json()
    assert "UNTRUSTED-LOG" not in (result.session / ".session/events.jsonl").read_text()
    status = session_status(result.session, root=root)
    assert status.last_check == checked
    assert status.last_outcome == "passed"


@pytest.mark.parametrize("name", [".env", ".env.local", "a.pem", "a.key", "id_rsa"])
def test_sensitive_files_never_copied_or_committed(authored, root, sandbox, name):
    (authored / "workspace" / name).write_text("fake-sensitive-fixture")
    result = start_session(authored, root=root, sandbox=sandbox)
    assert not (result.workspace / name).exists()
    assert name.encode() not in git(result.workspace, "ls-files")
    assert not (result.session / ".session/original" / name).exists()


def test_no_inherited_git_configuration_hooks_or_filters(
    authored, root, sandbox, monkeypatch, tmp_path
):
    marker = tmp_path / "executed"
    home = tmp_path / "fake-home"
    home.mkdir()
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
    hook.chmod(0o700)
    config = home / ".gitconfig"
    config.write_text(
        f"[core]\n hooksPath = {hooks}\n fsmonitor = {hook}\n"
        f'[filter "malicious"]\n clean = touch {marker}\n required = true\n'
        "[commit]\n gpgSign = true\n"
    )
    (authored / "workspace/.gitattributes").write_text("*.py filter=malicious\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(config))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(hooks))
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(hooks))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong-repo"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "wrong-index"))
    result = start_session(authored, root=root, sandbox=sandbox)
    assert not marker.exists()
    assert not (tmp_path / "wrong-repo").exists()
    assert not (tmp_path / "wrong-index").exists()
    assert (result.workspace / ".git/HEAD").is_file()
    assert (result.workspace / "code.py").read_text() == "value = 0\n"


@pytest.mark.parametrize(
    ("outcome", "statuses", "limit", "passed"),
    [
        (RunOutcome.PASSED, [TestStatus.PASSED], None, True),
        (RunOutcome.FAILED, [TestStatus.FAILED], None, False),
        (RunOutcome.ERRORED, [TestStatus.ERRORED], None, False),
        (RunOutcome.PASSED, [TestStatus.SKIPPED], None, False),
        (RunOutcome.PASSED, [], None, False),
        (RunOutcome.MISSING_RESULTS, [], None, False),
        (RunOutcome.LIMIT_EXCEEDED, [], "timeout", False),
        (RunOutcome.LIMIT_EXCEEDED, [], "memory", False),
    ],
)
def test_outcomes(authored, root, sandbox, outcome, statuses, limit, passed):
    started = start_session(authored, root=root, sandbox=sandbox)
    sandbox.result = RunResult(
        outcome,
        tuple(TestResult("case\x1b\n", "", "", s) for s in statuses),
        0,
        limit,
        "[patchground] UNTRUSTED-LOG",
    )
    checked = check_session(started.session, root=root, sandbox=sandbox)
    assert checked.passed is passed
    assert checked.limit == limit
    assert sum(checked.counts.values()) == len(statuses)
    assert all(t.id == "case" for t in checked.tests)
    assert checked.duration_seconds >= 0
    assert session_status(started.session, root=root).last_check == checked


def test_selection_and_read_only_status(authored, root, sandbox, monkeypatch, tmp_path):
    started = start_session(authored, root=root, sandbox=sandbox)
    before = state(started.session)
    monkeypatch.chdir(started.workspace)
    assert session_status(root=root).session == started.session
    assert session_status(started.workspace, root=root).session == started.session
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SessionError, match="select a session"):
        session_status(root=root)
    assert state(started.session) == before
    assert sandbox.runs == 0


def test_hidden_collision_and_busy_lock(authored, root, sandbox):
    started = start_session(authored, root=root, sandbox=sandbox)
    lock = started.session / ".session/lock"
    with lock.open("r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(SessionError, match="session busy"):
            check_session(started.session, root=root, sandbox=sandbox)
    (started.workspace / "private.py").write_text("collision")
    with pytest.raises(SessionError, match="collision"):
        check_session(started.session, root=root, sandbox=sandbox)
    (started.workspace / "private.py").unlink()
    assert check_session(started.session, root=root, sandbox=sandbox).passed


@pytest.mark.parametrize(
    "error", [SandboxError("image missing UNTRUSTED-LOG"), KeyboardInterrupt()]
)
def test_lock_release_and_error_event(authored, root, sandbox, error):
    started = start_session(authored, root=root, sandbox=sandbox)
    sandbox.error = error
    with pytest.raises(KeyboardInterrupt if isinstance(error, KeyboardInterrupt) else SessionError):
        check_session(started.session, root=root, sandbox=sandbox)
    assert sandbox.builds == 1
    status = session_status(started.session, root=root)
    assert status.last_outcome in ("environment_error", "interrupted")
    assert status.last_check is None
    assert "UNTRUSTED-LOG" not in (started.session / ".session/events.jsonl").read_text()
    sandbox.error = None
    assert check_session(started.session, root=root, sandbox=sandbox).passed


@pytest.mark.parametrize(
    "target",
    [
        "session.json",
        "manifest.json",
        "events.jsonl",
        "TICKET.md",
        "original",
        "hidden",
        "lock",
    ],
)
def test_metadata_symlinks_rejected(authored, root, sandbox, target, tmp_path):
    started = start_session(authored, root=root, sandbox=sandbox)
    path = started.session / ".session" / target
    moved = tmp_path / "moved"
    path.chmod(0o700)
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=moved.is_dir())
    with pytest.raises(SessionError, match="symlink"):
        session_status(started.session, root=root)
    with pytest.raises(SessionError, match="symlink"):
        check_session(started.session, root=root, sandbox=sandbox)


@pytest.mark.parametrize(
    "target",
    ["", ".session", "workspace", ".session/hidden/private.py", ".session/original/code.py"],
)
def test_session_tree_links_rejected(authored, root, sandbox, target, tmp_path):
    started = start_session(authored, root=root, sandbox=sandbox)
    path = started.session / target
    path.parent.chmod(0o700)
    moved = tmp_path / "redirect"
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=moved.is_dir())
    with pytest.raises(SessionError, match="symlink"):
        session_status(started.session, root=root)


@pytest.mark.parametrize("target", ["session.json", "manifest.json", "events.jsonl"])
@pytest.mark.parametrize(
    "content", ["{", "{}\n", '{"ts":"not-a-date","type":"check_run","data":{}}\n']
)
def test_corrupt_metadata(authored, root, sandbox, target, content):
    started = start_session(authored, root=root, sandbox=sandbox)
    (started.session / ".session" / target).write_text(content)
    with pytest.raises(SessionError, match="corrupt"):
        session_status(started.session, root=root)
    with pytest.raises(SessionError, match="corrupt"):
        check_session(started.session, root=root, sandbox=sandbox)
    assert sandbox.runs == 0


def test_metadata_paths_not_trusted(authored, root, sandbox, tmp_path):
    started = start_session(authored, root=root, sandbox=sandbox)
    path = started.session / ".session/session.json"
    record = json.loads(path.read_text())
    record["workspace"] = str(tmp_path)
    path.write_text(json.dumps(record))
    with pytest.raises(SessionError, match="corrupt"):
        check_session(started.session, root=root, sandbox=sandbox)


@pytest.mark.parametrize("special", [False, True])
def test_user_links_and_special_files_rejected(authored, root, sandbox, special):
    started = start_session(authored, root=root, sandbox=sandbox)
    entry = started.workspace / "unsafe"
    if special:
        os.mkfifo(entry)
    else:
        entry.symlink_to(authored / "TICKET.md")
    with pytest.raises(SessionError, match="symlink or special"):
        check_session(started.session, root=root, sandbox=sandbox)
    assert sandbox.runs == 0


def test_selection_normalizes_parent_segments(authored, root, sandbox):
    started = start_session(authored, root=root, sandbox=sandbox)
    assert session_status(started.workspace / "..", root=root).session == started.session
    with pytest.raises(SessionError, match="select a session"):
        session_status(started.workspace / "../../..", root=root)


def test_root_symlink_does_not_create_external_directories(authored, sandbox, tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    link = tmp_path / "redirect"
    link.symlink_to(external, target_is_directory=True)
    with pytest.raises(SessionError, match="symlink"):
        start_session(authored, root=link / "sessions", sandbox=sandbox)
    assert not list(external.iterdir())
    assert sandbox.builds == 0


@pytest.mark.parametrize("damage", ["truncated", "timestamp", "check_data", "counts", "version"])
def test_event_and_record_consistency(authored, root, sandbox, damage):
    started = start_session(authored, root=root, sandbox=sandbox)
    check_session(started.session, root=root, sandbox=sandbox)
    meta = started.session / ".session"
    events = meta / "events.jsonl"
    if damage == "version":
        path = meta / "session.json"
        record = json.loads(path.read_text())
        record["schema_version"] = 2
        path.write_text(json.dumps(record))
    elif damage == "truncated":
        events.write_text(events.read_text().rstrip("\n"))
    else:
        lines = [json.loads(line) for line in events.read_text().splitlines()]
        if damage == "timestamp":
            lines[-1]["ts"] = "not-a-date"
        elif damage == "check_data":
            lines[-1]["data"] = {"log_tail": "UNTRUSTED-LOG"}
        else:
            lines[-1]["data"]["counts"]["passed"] = 999
        events.write_text("".join(json.dumps(line) + "\n" for line in lines))
    with pytest.raises(SessionError, match="corrupt"):
        session_status(started.session, root=root)


def test_unknown_events_ignored_and_status_never_recreates_lock(authored, root, sandbox):
    started = start_session(authored, root=root, sandbox=sandbox)
    meta = started.session / ".session"
    events = meta / "events.jsonl"
    event = json.loads(events.read_text())
    event.update(type="future_event", data={"future": True})
    with events.open("a") as stream:
        stream.write(json.dumps(event) + "\n")
    assert session_status(started.session, root=root).last_check is None
    (meta / "lock").unlink()
    with pytest.raises(SessionError):
        session_status(started.session, root=root)
    assert not (meta / "lock").exists()
