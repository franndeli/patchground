"""Hermetic transport checks: no challenge commands execute on the host."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from patchground.packs import source
from patchground.packs.models import PackError


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "input"
    path.mkdir()
    git(path, "init", "--template=")
    git(path, "config", "user.name", "Transport Test")
    git(path, "config", "user.email", "transport@users.noreply.github.com")
    (path / "file").write_bytes(b"committed\r\n")
    git(path, "add", ".")
    git(path, "commit", "-m", "fixture")
    return path


def git(repo: Path, *args: str) -> bytes:
    executable = shutil.which("git")
    assert executable
    return subprocess.check_output([executable, "-C", str(repo), *args], stderr=subprocess.DEVNULL)


def test_committed_raw_snapshot_and_cleanup(repo: Path) -> None:
    commit = git(repo, "rev-parse", "HEAD").decode().strip()
    git(repo, "tag", "pinned")
    (repo / "file").write_bytes(b"dirty")
    (repo / "untracked").write_text("not committed")
    before = git(repo, "status", "--porcelain")
    with source.fetch_pack(repo, "pinned") as snapshot:
        assert snapshot.commit == commit
        assert snapshot.source == str(repo)
        assert snapshot.source_kind == "local"
        assert (snapshot.path / "file").read_bytes() == git(repo, "show", "pinned:file")
        assert sorted(p.name for p in snapshot.path.iterdir()) == ["file"]
        temporary = snapshot.path
        assert stat.S_IMODE(temporary.parent.stat().st_mode) == 0o700
    assert not temporary.exists()
    assert git(repo, "status", "--porcelain") == before


def test_no_source_configuration_hooks_filters_or_path_executable(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "executed"
    script = repo / "evil"
    script.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 1\n')
    script.chmod(0o755)
    (repo / ".gitattributes").write_text("* filter=evil export-subst\n")
    git(repo, "add", ".gitattributes")
    git(repo, "commit", "-m", "attributes")
    for key in ("core.fsmonitor", "filter.evil.smudge", "uploadpack.packObjectsHook"):
        git(repo, "config", key, str(script))
    git(repo, "config", "include.path", str(script))
    # Git placed in the source PATH must never even be probed.
    (repo / "git").write_bytes(script.read_bytes())
    (repo / "git").chmod(0o755)
    monkeypatch.setenv("PATH", str(repo) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(script))
    with source.fetch_pack(repo) as snapshot:
        assert (snapshot.path / "file").read_bytes() == b"committed\r\n"
    assert not marker.exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/repo",
        "ssh://example.test/repo",
        "git@example.test:repo",
        "file:///tmp/repo",
        "https://user:password@example.test/repo",
        "https://example.test/repo?token=fake",
        "https://example.test/repo#fragment",
        "https://example.test:invalid/repo",
    ],
)
def test_transport_policy(url: str) -> None:
    with pytest.raises(PackError), source.fetch_pack(url):
        pytest.fail("unsupported transport accepted")


def test_https_canonicalization() -> None:
    assert source._source("https://EXAMPLE.test:443/repo/") == (
        "https://example.test/repo",
        "https",
        None,
    )


@pytest.mark.parametrize("kind", ["symlink", "submodule", "lfs", "backslash"])
def test_unsupported_committed_content(repo: Path, kind: str) -> None:
    if kind == "symlink":
        (repo / "link").symlink_to("file")
        git(repo, "add", "link")
    elif kind == "submodule":
        commit = git(repo, "rev-parse", "HEAD").decode().strip()
        git(repo, "update-index", "--add", "--cacheinfo", f"160000,{commit},nested")
    elif kind == "backslash":
        (repo / "bad\\name").write_text("unsafe")
        git(repo, "add", ".")
    else:
        (repo / "pointer").write_text(
            "version https://git-lfs.github.com/spec/v1\noid sha256:fake\n"
        )
        git(repo, "add", ".")
    git(repo, "commit", "-m", "unsupported")
    with pytest.raises(PackError), source.fetch_pack(repo):
        pytest.fail("unsupported content accepted")


@pytest.mark.parametrize("limit,value", [("MAX_BYTES", 1), ("MAX_FILES", 0), ("TIMEOUT", 0)])
def test_limits(repo: Path, monkeypatch: pytest.MonkeyPatch, limit: str, value: int) -> None:
    monkeypatch.setattr(source, limit, value)
    with pytest.raises(PackError), source.fetch_pack(repo):
        pytest.fail("limit ignored")


def test_bare_packed_repository(repo: Path, tmp_path: Path) -> None:
    bare = tmp_path / "bare"
    git(repo, "clone", "--bare", str(repo), str(bare))
    git(bare, "gc")
    with source.fetch_pack(bare) as snapshot:
        assert (snapshot.path / "file").read_bytes() == b"committed\r\n"


def test_missing_ref_safe_error(repo: Path) -> None:
    with (
        pytest.raises(PackError, match="cannot read pack source or revision"),
        source.fetch_pack(repo, "private-reference-value"),
    ):
        pytest.fail("missing revision accepted")


def test_https_fetch_uses_isolated_policy(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = source._run_process
    fetched = False

    def intercept(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal fetched
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert environment["GIT_ALLOW_PROTOCOL"] == "https"
        assert "GIT_CONFIG_COUNT" not in environment
        assert "GIT_EXEC_PATH" not in environment
        assert "SSH_AUTH_SOCK" not in environment
        assert Path(command[0]).is_absolute()
        assert "credential.helper=" in command
        assert "http.followRedirects=false" in command
        if "fetch" in command:
            fetched = True
            assert command[-2:] == ["https://example.test/repo", "HEAD"]
            # Replace only the wire for a hermetic native Git transfer.
            command = [*command[:-2], str(repo), command[-1]]
            kwargs["env"] = {**environment, "GIT_ALLOW_PROTOCOL": "file"}
        return original(command, **kwargs)

    monkeypatch.setenv("GIT_CONFIG_COUNT", "999")
    monkeypatch.setenv("GIT_EXEC_PATH", str(repo))
    monkeypatch.setenv("SSH_AUTH_SOCK", str(repo / "socket"))
    monkeypatch.setattr(source, "_run_process", intercept)
    with source.fetch_pack("https://EXAMPLE.test:443/repo/") as snapshot:
        assert snapshot.source == "https://example.test/repo"
        assert snapshot.source_kind == "https"
        assert (snapshot.path / "file").read_bytes() == b"committed\r\n"
    assert fetched


@pytest.mark.parametrize("interruption", [subprocess.TimeoutExpired("git", 1), KeyboardInterrupt()])
def test_git_helpers_are_killed_with_parent(interruption, tmp_path, monkeypatch) -> None:
    import signal
    from unittest.mock import MagicMock

    process = MagicMock()
    process.pid = 12345
    process.communicate.side_effect = [interruption, (b"", None)]
    popen = MagicMock()
    popen.return_value.__enter__.return_value = process
    kill = MagicMock()
    monkeypatch.setattr(source.subprocess, "Popen", popen)
    monkeypatch.setattr(source.os, "killpg", kill)
    with pytest.raises(type(interruption)):
        source._run_process(["git"], cwd=tmp_path, env={}, timeout=1)
    kill.assert_called_once_with(process.pid, signal.SIGKILL)
    assert popen.call_args.kwargs["start_new_session"] is True
    assert process.communicate.call_count == 2


def test_timeout_does_not_leak_subprocess_details(monkeypatch: pytest.MonkeyPatch) -> None:
    def timed_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("sensitive-command", 1, output=b"private-output")

    monkeypatch.setattr(source, "_run_process", timed_out)
    with (
        pytest.raises(PackError, match=r"^pack transport timed out$"),
        source.fetch_pack("https://example.test/repo"),
    ):
        pytest.fail("timeout ignored")


def test_symlinked_git_data_rejected(repo: Path, tmp_path: Path) -> None:
    objects = repo / ".git" / "objects"
    moved = tmp_path / "objects"
    objects.rename(moved)
    objects.symlink_to(moved, target_is_directory=True)
    with pytest.raises(PackError), source.fetch_pack(repo):
        pytest.fail("symlinked metadata accepted")


def test_executable_mode_and_sha256(tmp_path: Path) -> None:
    repo = tmp_path / "sha256"
    repo.mkdir()
    git(repo, "init", "--object-format=sha256", "--template=")
    git(repo, "config", "user.name", "Transport Test")
    git(repo, "config", "user.email", "transport@users.noreply.github.com")
    (repo / "executable").write_text("raw content")
    (repo / "executable").chmod(0o755)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture")
    with source.fetch_pack(repo) as snapshot:
        assert len(snapshot.commit) == 64
        assert (snapshot.path / "executable").stat().st_mode & stat.S_IXUSR


def test_corrupt_object_cannot_claim_original_commit(repo: Path) -> None:
    import zlib

    blob = git(repo, "rev-parse", "HEAD:file").decode().strip()
    object_path = repo / ".git" / "objects" / blob[:2] / blob[2:]
    object_path.chmod(0o600)
    object_path.write_bytes(zlib.compress(b"blob 6\0forged"))
    with pytest.raises(PackError), source.fetch_pack(repo):
        pytest.fail("forged object identity accepted")


def test_linked_worktree_fails_closed(repo: Path, tmp_path: Path) -> None:
    worktree = tmp_path / "linked"
    git(repo, "worktree", "add", "--detach", str(worktree))
    with pytest.raises(PackError), source.fetch_pack(worktree):
        pytest.fail("external worktree metadata followed")
