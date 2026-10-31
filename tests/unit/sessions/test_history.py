"""Checkpoint evidence, private Git isolation and legacy compatibility."""

import json
import os
import subprocess
import zlib
from pathlib import Path

import pytest

from patchground.sessions import (
    check_session,
    history_for_session,
    session_status,
    start_session,
    store,
)
from patchground.sessions import history as checkpoints


@pytest.fixture(autouse=True)
def isolated_ignore_environment(monkeypatch, tmp_path):
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def git_bytes(workspace: Path) -> dict[str, bytes]:
    return {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in (workspace / ".git").rglob("*")
        if path.is_file()
    }


def blobs(session: Path, ref: str) -> set[bytes]:
    repository = session / ".session/history.git"
    objects = [zlib.decompress(path.read_bytes()) for path in (repository / "objects").glob("*/*")]
    return {data.split(b"\0", 1)[1] for data in objects if data.startswith(b"blob ")}


def test_initial_check_history_preserves_git_and_filters(authored, root, sandbox, tmp_path):
    started = start_session(authored, root=root, sandbox=sandbox)
    assert started.history.state == "recorded"
    workspace = started.workspace
    (workspace / "code.py").write_text("staged = True\n")
    subprocess.run(["git", "-C", str(workspace), "add", "code.py"], check=True, capture_output=True)
    (workspace / "code.py").write_text("unstaged = True\n")
    marker = tmp_path / "executed"
    with (workspace / ".git/config").open("a") as stream:
        stream.write(
            f'\n[filter "danger"]\n clean = touch {marker}\n smudge = touch {marker}\n'
            f"[core]\n hooksPath = {tmp_path}\n fsmonitor = touch {marker}\n"
        )
    (workspace / ".gitattributes").write_text("* filter=danger ident\n")
    (workspace / ".gitignore").write_text(
        "*.ignored\n!keep.ignored\ncache/\n/root-only\n**/skip.bin\n"
    )
    (workspace / "nested").mkdir()
    (workspace / "nested/.gitignore").write_text("local.txt\n")
    for name in (
        "a.ignored",
        "keep.ignored",
        "root-only",
        "nested/root-only",
        "nested/skip.bin",
        "nested/local.txt",
        ".env.local",
        "secret.pem",
    ):
        (workspace / name).write_text("payload:" + name)
    (workspace / "cache").mkdir()
    (workspace / "cache/ordinary").write_text("ignored-directory")
    # Repository info excludes apply even to files tracked in the learner repository.
    (workspace / ".git/info").mkdir()
    (workspace / ".git/info/exclude").write_text("code.py\n")
    before = git_bytes(workspace)
    result = check_session(started.session, root=root, sandbox=sandbox)
    assert result.passed and result.history.state == "recorded"
    assert git_bytes(workspace) == before
    assert not marker.exists()
    saved = blobs(started.session, result.history.ref)
    assert b"payload:keep.ignored" in saved
    assert b"payload:nested/root-only" in saved
    assert b"unstaged = True\n" not in saved
    assert b"# synthetic private fixture\n" not in saved
    for payload in (
        b"payload:a.ignored",
        b"payload:root-only",
        b"payload:nested/skip.bin",
        b"payload:nested/local.txt",
        b"payload:.env.local",
        b"payload:secret.pem",
        b"ignored-directory",
    ):
        assert payload not in saved
    history = history_for_session(started.session, root=root)
    assert history.enabled and history.availability == "available"
    assert [entry.kind for entry in history.snapshots] == ["initial", "check"]
    assert history.snapshots[-1].check_outcome == "passed"
    assert all(
        entry.ts.tzinfo is not None and len(entry.commit) == 40 for entry in history.snapshots
    )
    event = store.load(started.session)[2][-1]
    assert event.data == result.model_dump(mode="json")


def test_checkpoint_uses_captured_editable_input(authored, root, sandbox, monkeypatch):
    started = start_session(authored, root=root, sandbox=sandbox)
    original_run = sandbox.run_check

    def run(*args):
        (started.workspace / "code.py").write_text("edited-during-check")
        return original_run(*args)

    monkeypatch.setattr(sandbox, "run_check", run)
    checked = check_session(started.session, root=root, sandbox=sandbox)
    saved = blobs(started.session, checked.history.ref)
    assert b"value = 0\n" in saved
    assert b"edited-during-check" not in saved
    assert b"# synthetic private fixture\n" not in saved


@pytest.mark.parametrize("legacy", [False, True])
def test_disabled_and_legacy_never_create_history(authored, root, sandbox, monkeypatch, legacy):
    started = start_session(authored, root=root, sandbox=sandbox, history=False)
    if legacy:
        metadata = started.session / ".session/session.json"
        data = json.loads(metadata.read_text())
        data.pop("history_enabled")
        metadata.write_text(json.dumps(data))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("Git invoked"))
    checked = check_session(started.session, root=root, sandbox=sandbox)
    assert checked.passed and checked.history.state == "disabled"
    assert history_for_session(started.session, root=root).availability == "disabled"
    assert not (started.session / ".session/history.git").exists()


@pytest.mark.parametrize("error", [OSError, RuntimeError, KeyboardInterrupt])
def test_capture_failure_keeps_check_evidence_and_retry(
    authored, root, sandbox, monkeypatch, error
):
    started = start_session(authored, root=root, sandbox=sandbox)
    original = checkpoints._repository

    def fail(*args):
        raise error("unsafe arbitrary detail must not escape")

    monkeypatch.setattr(checkpoints, "_repository", fail)
    result = check_session(started.session, root=root, sandbox=sandbox)
    assert result.passed and result.counts["passed"] == 1
    assert result.history.state == "unavailable" and result.history.ref is None
    assert "unsafe arbitrary" not in result.model_dump_json()
    assert session_status(started.session, root=root).last_check == result
    assert history_for_session(started.session, root=root).availability == "unavailable"
    monkeypatch.setattr(checkpoints, "_repository", original)
    retry = check_session(started.session, root=root, sandbox=sandbox)
    assert retry.history.state == "recorded"
    assert len(history_for_session(started.session, root=root).snapshots) == 2


@pytest.mark.parametrize("attack", ["config", "symlink", "hardlink", "hook", "corrupt"])
def test_unsafe_private_metadata_is_unavailable_without_execution(
    authored,
    root,
    sandbox,
    monkeypatch,
    tmp_path,
    attack,
):
    started = start_session(authored, root=root, sandbox=sandbox)
    repository = started.session / ".session/history.git"
    target = repository / "config"
    if attack == "config":
        target.write_text("[include]\n path = hostile\n")
    elif attack == "symlink":
        target.unlink()
        target.symlink_to(tmp_path / "missing")
    elif attack == "hardlink":
        os.link(target, tmp_path / "shared")
    elif attack == "hook":
        (repository / "hooks").mkdir()
        (repository / "hooks/post-checkout").write_text("hostile")
    else:
        next((repository / "objects").glob("*/*")).write_bytes(b"broken")
    before = (started.session / ".session/events.jsonl").read_bytes()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("Git read invoked"))
    result = history_for_session(started.session, root=root)
    assert result.availability == "unavailable" and not result.snapshots
    assert (started.session / ".session/events.jsonl").read_bytes() == before


def test_orphan_checkpoint_not_advertised(authored, root, sandbox):
    started = start_session(authored, root=root, sandbox=sandbox)
    orphan = checkpoints.capture(
        started.session / ".session",
        started.workspace,
        enabled=True,
        kind="check",
        check_outcome="passed",
    )
    assert orphan.state == "recorded"
    saved = history_for_session(started.session, root=root)
    assert [entry.ref for entry in saved.snapshots] == [started.history.ref]


def test_shared_objects_deduplicated_and_failed_publish_retry(authored, root, sandbox, monkeypatch):
    started = start_session(authored, root=root, sandbox=sandbox)
    repository = started.session / ".session/history.git"
    initial = set((repository / "objects").glob("*/*"))
    original = checkpoints._publish

    def fail_after_publish(*args):
        original(*args)
        raise OSError("publication acknowledgement failed")

    monkeypatch.setattr(checkpoints, "_publish", fail_after_publish)
    failed = check_session(started.session, root=root, sandbox=sandbox)
    assert failed.passed and failed.history.state == "unavailable"
    # Its fully written but unrecorded ref remains an orphan; reading never invents evidence.
    assert len(history_for_session(started.session, root=root).snapshots) == 1
    monkeypatch.setattr(checkpoints, "_publish", original)
    checked = check_session(started.session, root=root, sandbox=sandbox)
    assert checked.history.state == "recorded"
    assert len(history_for_session(started.session, root=root).snapshots) == 2
    # Identical input adds only one commit per capture, sharing every tree and blob.
    assert len(set((repository / "objects").glob("*/*")) - initial) == 2
    assert len(list((repository / "refs/patchground/check").iterdir())) == 2


def test_redirected_history_never_writes_user_git(authored, root, sandbox):
    started = start_session(authored, root=root, sandbox=sandbox, history=False)
    target = started.session / ".session/history.git"
    target.symlink_to(started.workspace / ".git", target_is_directory=True)
    before = git_bytes(started.workspace)
    result = checkpoints.capture(
        started.session / ".session",
        started.workspace,
        enabled=True,
        kind="check",
        check_outcome="passed",
    )
    assert result.state == "unavailable"
    assert git_bytes(started.workspace) == before


def test_submitted_history_without_workspace_or_execution(authored, root, sandbox, monkeypatch):
    import shutil

    from patchground.sessions import check_submission, commit_submission, prepare_submission

    started = start_session(authored, root=root, sandbox=sandbox)
    check_session(started.session, root=root, sandbox=sandbox)
    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        commit_submission(snapshot, {}, "", result)
    shutil.rmtree(started.workspace)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("Git read invoked"))
    before = (started.session / ".session/events.jsonl").read_bytes()
    saved = history_for_session(started.session, root=root)
    assert saved.availability == "available"
    assert len(saved.snapshots) == 2
    assert (started.session / ".session/events.jsonl").read_bytes() == before


def test_captured_ignore_escaping_wildcards_and_negated_parent(tmp_path):
    (tmp_path / ".gitignore").write_text(
        r"\#literal"
        + "\n"
        + r"\!literal"
        + "\n"
        + "[[:digit:]].log\n"
        + "excluded/\n!excluded/keep\n**/deep.tmp\n"
        + r"with\ space"
        + "\n"
    )
    for name in ("#literal", "!literal", "3.log", "a.log", "with space", "ordinary"):
        (tmp_path / name).touch()
    (tmp_path / "excluded").mkdir()
    (tmp_path / "excluded/keep").touch()
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/deep.tmp").touch()
    (tmp_path / "nested/.gitignore").write_text("*.nested\n!keep.nested\n")
    (tmp_path / "nested/omit.nested").touch()
    (tmp_path / "nested/keep.nested").touch()
    from patchground.sessions import git
    from patchground.sessions.history_ignore import resolve

    git.initialize(tmp_path)
    meta = tmp_path / "metadata"
    meta.mkdir()
    names = [
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    ]
    native = subprocess.run(
        ["git", "-C", str(tmp_path), "check-ignore", "--no-index", "-z", "--stdin"],
        input=b"\0".join(os.fsencode(name) for name in names) + b"\0",
        capture_output=True,
        check=True,
    )
    expected = {os.fsencode(name) for name in names} - set(native.stdout.split(b"\0"))
    before = git_bytes(tmp_path)
    status = checkpoints.capture(
        meta, tmp_path, enabled=True, kind="initial", rules=resolve(tmp_path)
    )
    assert status.state == "recorded"
    repository = meta / "history.git"
    actual = subprocess.run(
        ["git", "--git-dir=" + str(repository), "ls-tree", "-rz", "--name-only", status.ref],
        capture_output=True,
        check=True,
    ).stdout
    assert set(actual.rstrip(b"\0").split(b"\0")) == expected
    assert git_bytes(tmp_path) == before


@pytest.mark.parametrize("origin", ["global", "system", "xdg", "local", "override"])
def test_native_git_global_and_configured_exclusions(
    authored, root, sandbox, monkeypatch, tmp_path, origin
):
    started = start_session(authored, root=root, sandbox=sandbox)
    workspace = started.workspace
    rules = tmp_path / "exclusions"
    rules.write_text("private-*\n!private-keep\n")
    home = Path(os.environ["HOME"])
    if origin == "xdg":
        rules = home / ".config/git/ignore"
        rules.parent.mkdir(parents=True)
        rules.write_text("private-*\n!private-keep\n")
    else:
        if origin == "global":
            config = home / ".gitconfig"
        elif origin == "local":
            config = workspace / ".git/config"
        else:
            config = tmp_path / "override-config"
            monkeypatch.setenv(
                "GIT_CONFIG_SYSTEM" if origin == "system" else "GIT_CONFIG_GLOBAL", str(config)
            )
            if origin == "system":
                monkeypatch.delenv("GIT_CONFIG_NOSYSTEM")
        with config.open("a") as stream:
            stream.write(f"\n[core]\n excludesFile = {rules}\n")
    (workspace / "private-secret").write_text("global-private-payload")
    (workspace / "private-keep").write_text("negated-global-payload")
    before = git_bytes(workspace)
    native = subprocess.run(
        ["git", "-C", str(workspace), "check-ignore", "--no-index", "private-secret"],
        capture_output=True,
    )
    assert native.returncode == 0
    result = check_session(started.session, root=root, sandbox=sandbox)
    assert result.history.state == "recorded"
    assert b"global-private-payload" not in blobs(started.session, result.history.ref)
    assert b"negated-global-payload" in blobs(started.session, result.history.ref)
    assert git_bytes(workspace) == before


@pytest.mark.parametrize(
    "unsafe",
    [
        "include",
        "includeIf",
        "inapplicable-includeIf",
        "symlink",
        "hardlink",
        "fifo",
        "relative",
        "missing-git",
        "gitfile",
        "worktree",
        "environment",
        "environment-config",
        "global-symlink",
    ],
)
def test_unresolved_exclusions_fail_closed_preserving_check(
    authored, root, sandbox, monkeypatch, tmp_path, unsafe
):
    started = start_session(authored, root=root, sandbox=sandbox)
    workspace = started.workspace
    info = workspace / ".git/info"
    info.mkdir()
    target = info / "exclude"
    secret = tmp_path / "exclusions"
    secret.write_text("code.py\n")
    if unsafe in ("include", "includeIf", "inapplicable-includeIf", "relative", "worktree"):
        content = {
            "include": f"[include]\n path = {secret}\n",
            "includeIf": f'[includeIf "gitdir:**/workspace/"]\n path = {secret}\n',
            "inapplicable-includeIf": (
                f'[includeIf "gitdir:/never-applicable/"]\n path = {secret}\n'
            ),
            "relative": "[core]\n excludesFile = relative-ignore\n",
            "worktree": "[extensions]\n worktreeConfig = true\n",
        }[unsafe]
        with (workspace / ".git/config").open("a") as stream:
            stream.write("\n" + content)
    elif unsafe == "symlink":
        target.symlink_to(secret)
    elif unsafe == "hardlink":
        os.link(secret, target)
    elif unsafe == "fifo":
        os.mkfifo(target)
    elif unsafe == "missing-git":
        import shutil

        shutil.rmtree(workspace / ".git")
    elif unsafe == "gitfile":
        import shutil

        shutil.rmtree(workspace / ".git")
        (workspace / ".git").write_text("gitdir: elsewhere\n")
    elif unsafe == "environment":
        monkeypatch.setenv("GIT_DIR", str(tmp_path))
    elif unsafe == "environment-config":
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.excludesFile")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(secret))
    else:
        (Path(os.environ["HOME"]) / ".gitconfig").symlink_to(secret)
    # The checker excludes .git itself, so unsafe metadata must not affect checks.
    before = git_bytes(workspace) if unsafe not in ("fifo", "missing-git", "gitfile") else None
    checked = check_session(started.session, root=root, sandbox=sandbox)
    assert checked.passed and checked.history.state == "unavailable"
    assert checked.history.ref is None
    assert session_status(started.session, root=root).last_check == checked
    if before is not None:
        assert git_bytes(workspace) == before
    assert len(history_for_session(started.session, root=root).snapshots) == 1


def test_ignore_inputs_are_captured_before_check(authored, root, sandbox):
    started = start_session(authored, root=root, sandbox=sandbox)
    info = started.workspace / ".git/info"
    info.mkdir()
    (info / "exclude").write_text("code.py\n")
    (started.workspace / "code.py").write_text("boundary-private-payload")
    original = sandbox.run_check

    def run(*args):
        (info / "exclude").write_text("")
        return original(*args)

    sandbox.run_check = run
    checked = check_session(started.session, root=root, sandbox=sandbox)
    assert checked.passed and checked.history.state == "recorded"
    assert b"boundary-private-payload" not in blobs(started.session, checked.history.ref)


def test_configuration_stays_in_memory(authored, root, sandbox, monkeypatch):
    home = Path(os.environ["HOME"])
    private_value = "obviously-fake-sensitive-config-marker"
    (home / ".gitconfig").write_text(f"[credential]\n helper = {private_value}\n")
    original = Path.write_bytes

    def write(path, data):
        assert private_value.encode() not in data
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", write)
    started = start_session(authored, root=root, sandbox=sandbox)
    assert started.history.state == "recorded"


def test_ignorecase_and_local_precedence(authored, root, sandbox):
    started = start_session(authored, root=root, sandbox=sandbox)
    home = Path(os.environ["HOME"])
    (home / "global-ignore").write_text("global-only.txt\n")
    (home / ".gitconfig").write_text(f"[core]\n excludesFile = {home / 'global-ignore'}\n")
    (home / "local-ignore").write_text("PRIVATE.txt\n")
    with (started.workspace / ".git/config").open("a") as stream:
        stream.write(f"\n[core]\n ignoreCase = true\n excludesFile = {home / 'local-ignore'}\n")
    (started.workspace / "private.txt").write_text("case-private-payload")
    (started.workspace / "global-only.txt").write_text("local-override-visible-payload")
    checked = check_session(started.session, root=root, sandbox=sandbox)
    assert checked.history.state == "recorded"
    saved = blobs(started.session, checked.history.ref)
    assert b"case-private-payload" not in saved
    assert b"local-override-visible-payload" in saved


def test_system_path_discovery_is_native_and_bounded(
    authored, root, sandbox, monkeypatch, tmp_path
):
    started = start_session(authored, root=root, sandbox=sandbox)
    config = tmp_path / "system-config"
    rules = tmp_path / "system-ignore"
    rules.write_text("system-private.txt\n")
    config.write_text(f"[core]\n excludesFile = {rules}\n")
    (started.workspace / "system-private.txt").write_text("system-discovery-private-payload")
    monkeypatch.delenv("GIT_CONFIG_NOSYSTEM")
    original = subprocess.run
    discoveries = []

    def run(command, **kwargs):
        if command[-2:] == ["var", "GIT_CONFIG_SYSTEM"]:
            assert kwargs["cwd"] != started.workspace
            assert "GIT_CONFIG_SYSTEM" not in kwargs["env"]
            discoveries.append(command)
            return subprocess.CompletedProcess(command, 0, os.fsencode(config) + b"\n", b"")
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    checked = check_session(started.session, root=root, sandbox=sandbox)
    assert discoveries and checked.history.state == "recorded"
    assert b"system-discovery-private-payload" not in blobs(started.session, checked.history.ref)
