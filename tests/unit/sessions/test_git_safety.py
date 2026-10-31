"""Executable discovery must never turn editable input into host code."""

import os
import shlex
import shutil
from pathlib import Path

import pytest

from patchground.sessions import SessionError, check_session, git, start_session
from patchground.sessions.history_ignore import resolve


def git_bytes(workspace: Path) -> dict[str, bytes]:
    return {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in (workspace / ".git").rglob("*")
        if path.is_file()
    }


def fake_git(path: Path, marker: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\nprintf executed > {shlex.quote(str(marker))}\nexit 0\n")
    path.chmod(0o700)


@pytest.fixture(autouse=True)
def clean_git_environment(monkeypatch, tmp_path):
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.mark.parametrize(
    "entry", ["empty", "dot", "relative", "absolute", "symlink", "symlink-dir", "original"]
)
@pytest.mark.parametrize("fallback", [False, True])
def test_history_never_executes_workspace_git(
    authored, root, sandbox, monkeypatch, tmp_path, entry, fallback
):
    trusted = Path(shutil.which("git", path=os.defpath)).resolve(strict=True)
    marker = tmp_path / "executed"
    if entry == "original":
        fake_git(authored / "workspace/bin/git", marker)
    started = start_session(authored, root=root, sandbox=sandbox)
    workspace = started.workspace
    binary = workspace / "bin/git"
    fake_git(binary, marker)
    if entry in ("dot", "empty"):
        fake_git(workspace / "git", marker)
        search = "." if entry == "dot" else ""
    elif entry == "original":
        search = str(started.session / ".session/original/bin")
    elif entry == "relative":
        search = "bin"
    elif entry == "absolute":
        search = str(binary.parent)
    elif entry == "symlink":
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "git").symlink_to(binary)
        search = str(outside)
    else:
        outside = tmp_path / "outside"
        outside.symlink_to(binary.parent, target_is_directory=True)
        search = str(outside)
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("PATH", search + (os.pathsep + str(trusted.parent) if fallback else ""))
    before = git_bytes(workspace)
    checked = check_session(started.session, root=root, sandbox=sandbox)
    assert not marker.exists()
    assert checked.passed
    assert checked.history.state == ("recorded" if fallback else "unavailable")
    assert git_bytes(workspace) == before


def test_config_query_rejects_absolute_workspace_git_outside_cwd(
    authored, root, sandbox, monkeypatch, tmp_path
):
    started = start_session(authored, root=root, sandbox=sandbox)
    marker = tmp_path / "executed"
    fake_git(started.workspace / "bin/git", marker)
    monkeypatch.setenv("PATH", str(started.workspace / "bin"))
    before = git_bytes(started.workspace)
    assert resolve(started.workspace) is None
    assert not marker.exists()
    assert git_bytes(started.workspace) == before


@pytest.mark.parametrize("fallback", [False, True])
def test_initial_git_never_executes_workspace_candidate(monkeypatch, tmp_path, fallback):
    workspace = tmp_path / "workspace"
    marker = tmp_path / "executed"
    fake_git(workspace / "git", marker)
    trusted = Path(shutil.which("git", path=os.defpath)).resolve(strict=True)
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("PATH", "." + (os.pathsep + str(trusted.parent) if fallback else ""))
    if fallback:
        git.initialize(workspace)
        assert (workspace / ".git/HEAD").is_file()
    else:
        with pytest.raises(SessionError, match="safe Git executable unavailable"):
            git.initialize(workspace)
        assert not (workspace / ".git").exists()
    assert not marker.exists()


@pytest.mark.parametrize("operation", ["initial", "check"])
def test_authored_source_candidate_is_rejected_outside_source_cwd(
    authored, root, sandbox, monkeypatch, tmp_path, operation
):
    trusted = Path(shutil.which("git", path=os.defpath)).resolve(strict=True)
    marker = tmp_path / "executed"
    fake_git(authored / "bin/git", marker)
    if operation == "check":
        started = start_session(authored, root=root, sandbox=sandbox)
        before = git_bytes(started.workspace)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(authored / "bin") + os.pathsep + str(trusted.parent))
    if operation == "initial":
        started = start_session(authored, root=root, sandbox=sandbox)
        assert started.history.state == "recorded"
        assert (started.workspace / ".git/HEAD").is_file()
    else:
        checked = check_session(started.session, root=root, sandbox=sandbox)
        assert checked.history.state == "recorded"
        assert git_bytes(started.workspace) == before
    assert not marker.exists()


def test_recorded_source_may_be_removed(authored, root, sandbox, monkeypatch, tmp_path):
    started = start_session(authored, root=root, sandbox=sandbox)
    shutil.rmtree(authored)
    monkeypatch.chdir(tmp_path)
    before = git_bytes(started.workspace)
    checked = check_session(started.session, root=root, sandbox=sandbox)
    assert checked.passed and checked.history.state == "recorded"
    assert git_bytes(started.workspace) == before


def test_resolver_checks_resolved_input_root_without_execution(monkeypatch, tmp_path):
    source = tmp_path / "source"
    marker = tmp_path / "executed"
    fake_git(source / "bin/git", marker)
    alias = tmp_path / "source-alias"
    alias.symlink_to(source, target_is_directory=True)
    monkeypatch.setenv("PATH", str(source / "bin"))
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: pytest.fail("candidate executed"))
    with pytest.raises(SessionError, match="safe Git executable unavailable"):
        git.resolve_executable(alias)
    assert not marker.exists()


def test_bound_git_is_reused_if_path_changes_during_check(
    authored, root, sandbox, monkeypatch, tmp_path
):
    started = start_session(authored, root=root, sandbox=sandbox)
    marker = tmp_path / "executed"
    fake_git(started.workspace / "bin/git", marker)
    before = git_bytes(started.workspace)
    original = sandbox.run_check

    def run(*args):
        monkeypatch.setenv("PATH", str(started.workspace / "bin"))
        return original(*args)

    sandbox.run_check = run
    checked = check_session(started.session, root=root, sandbox=sandbox)
    assert checked.passed and checked.history.state == "recorded"
    assert git_bytes(started.workspace) == before
    assert not marker.exists()


def test_normal_installation_symlink_is_supported(monkeypatch, tmp_path):
    trusted = Path(shutil.which("git", path=os.defpath)).resolve(strict=True)
    installation = tmp_path / "installation"
    installation.mkdir()
    (installation / "git").symlink_to(trusted)
    monkeypatch.setenv("PATH", str(installation))
    assert git.resolve_executable(tmp_path / "learner") == str(trusted)
