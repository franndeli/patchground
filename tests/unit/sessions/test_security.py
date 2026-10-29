"""Deterministic regressions for executable, copy and mutable-metadata races."""

import os
import shutil
import stat
from pathlib import Path

import pytest

from patchground.sessions import (
    SessionError,
    check_session,
    files,
    session_status,
    start_session,
    store,
)


def test_relative_git_path_is_bound_before_workspace_cwd(
    authored, root, sandbox, tmp_path, monkeypatch
):
    trusted_git = shutil.which("git")
    assert trusted_git is not None
    caller = tmp_path / "caller"
    (caller / "bin").mkdir(parents=True)
    (caller / "bin/git").symlink_to(Path(trusted_git).resolve(strict=True))
    marker = tmp_path / "fake-git-executed"
    fake = authored / "workspace/bin/git"
    fake.parent.mkdir()
    fake.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
    fake.chmod(0o700)
    monkeypatch.chdir(caller)
    monkeypatch.setenv("PATH", "bin:/usr/bin:/bin")
    assert shutil.which("git") == "bin/git"
    started = start_session(authored, root=root, sandbox=sandbox)
    assert (started.workspace / ".git/HEAD").is_file()
    assert not marker.exists()


@pytest.mark.parametrize("replacement", ["file", "directory", "fifo"])
def test_later_copy_entry_replaced_during_copy(
    authored, root, sandbox, tmp_path, monkeypatch, replacement
):
    started = start_session(authored, root=root, sandbox=sandbox)
    outside = tmp_path / ".env"
    outside.write_bytes(b"synthetic-outside-bytes")
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "data").write_bytes(outside.read_bytes())
    later = started.workspace / "z-later"
    if replacement == "directory":
        later.mkdir()
        (later / "data").write_text("safe")
    else:
        later.write_text("safe")
    original = shutil.copyfileobj
    copied = []
    swapped = False

    def swap(reader, writer, *args):
        nonlocal swapped
        if not swapped:
            swapped = True
            if replacement == "directory":
                later.rename(started.workspace / "old-directory")
                later.symlink_to(outside_dir, target_is_directory=True)
            else:
                later.unlink()
                if replacement == "fifo":
                    os.mkfifo(later)
                else:
                    later.symlink_to(outside)
        data = reader.read()
        copied.append(data)
        assert b"synthetic-outside-bytes" not in data
        reader.seek(0)
        return original(reader, writer, *args)

    monkeypatch.setattr(shutil, "copyfileobj", swap)
    with pytest.raises(SessionError):
        check_session(started.session, root=root, sandbox=sandbox)
    assert swapped and copied
    assert sandbox.runs == 0
    assert session_status(started.session, root=root).last_outcome == "environment_error"


def test_open_directory_is_pinned_when_replaced_during_child_copy(tmp_path, monkeypatch):
    source, destination, outside = (tmp_path / name for name in ("source", "dest", "outside"))
    for directory in (source / "nested", destination, outside):
        directory.mkdir(parents=True)
    (source / "nested/a").write_bytes(b"safe-first")
    (source / "nested/z").write_bytes(b"safe-later")
    (outside / "z").write_bytes(b"synthetic-outside-bytes")
    original = shutil.copyfileobj
    swapped = False

    def swap(reader, writer, *args):
        nonlocal swapped
        if not swapped:
            swapped = True
            (source / "nested").rename(source / "old")
            (source / "nested").symlink_to(outside, target_is_directory=True)
        return original(reader, writer, *args)

    monkeypatch.setattr(shutil, "copyfileobj", swap)
    with pytest.raises(SessionError, match="changed"):
        files.copy_tree(source, destination)
    assert (destination / "nested/z").read_bytes() == b"safe-later"


def test_source_ancestor_replaced_before_open_is_rejected(tmp_path, monkeypatch):
    parent, destination, outside = (tmp_path / name for name in ("parent", "dest", "outside"))
    (parent / "source").mkdir(parents=True)
    destination.mkdir()
    (outside / "source").mkdir(parents=True)
    (outside / "source/data").write_bytes(b"synthetic-outside-bytes")
    original = os.open
    swapped = False

    def swap(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "parent" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            parent.rename(tmp_path / "old-parent")
            parent.symlink_to(outside, target_is_directory=True)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap)
    with pytest.raises(SessionError):
        files.copy_tree(parent / "source", destination)
    assert swapped and not list(destination.iterdir())


def test_copy_permissions_come_from_open_inode_without_special_bits(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "dest"
    source.mkdir()
    destination.mkdir()
    entry = source / "executable"
    entry.write_text("synthetic executable")
    entry.chmod(0o6751)
    files.copy_tree(source, destination)
    assert stat.S_IMODE((destination / "executable").stat().st_mode) == 0o751


@pytest.mark.parametrize(
    "name", ["events.jsonl", "lock", "session.json", "manifest.json", "TICKET.md"]
)
def test_preplanted_metadata_hardlink_rejected_unchanged(authored, root, sandbox, tmp_path, name):
    started = start_session(authored, root=root, sandbox=sandbox)
    target = started.session / ".session" / name
    external = tmp_path / "external"
    external.write_bytes(target.read_bytes())
    before = external.read_bytes()
    target.unlink()
    target.hardlink_to(external)
    with pytest.raises(SessionError, match="hardlinks"):
        session_status(started.session, root=root)
    with pytest.raises(SessionError, match="hardlinks"):
        check_session(started.session, root=root, sandbox=sandbox)
    assert external.read_bytes() == before
    assert sandbox.runs == 0


def test_events_and_lock_replaced_during_sandbox_do_not_modify_git(
    authored, root, sandbox, monkeypatch
):
    started = start_session(authored, root=root, sandbox=sandbox)
    index = started.workspace / ".git/index"
    before = index.read_bytes()
    ran = False

    def replace(*args):
        nonlocal ran
        ran = True
        for name in ("events.jsonl", "lock"):
            target = started.session / ".session" / name
            target.unlink()
            target.hardlink_to(index)
        return sandbox.result

    monkeypatch.setattr(sandbox, "run_check", replace)
    with pytest.raises(SessionError, match="hardlinks"):
        check_session(started.session, root=root, sandbox=sandbox)
    assert ran
    assert index.read_bytes() == before


@pytest.mark.parametrize("name", ["events.jsonl", "lock"])
def test_metadata_hardlink_swapped_at_open_is_rejected(
    authored, root, sandbox, tmp_path, monkeypatch, name
):
    started = start_session(authored, root=root, sandbox=sandbox)
    meta = started.session / ".session"
    external = tmp_path / "external"
    external.write_bytes((meta / name).read_bytes())
    before = external.read_bytes()
    original = os.open

    def swap(path, flags, *args, **kwargs):
        if path == name and kwargs.get("dir_fd") is not None:
            (meta / name).unlink()
            (meta / name).hardlink_to(external)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap)
    with pytest.raises(SessionError, match="hardlinks"):
        if name == "events.jsonl":
            store.append_event(meta, "future_event", {})
        else:
            with store.locked(meta):
                pytest.fail("hardlinked lock accepted")
    assert external.read_bytes() == before


@pytest.mark.parametrize("replacement", ["file", "directory", "fifo"])
def test_copy_replacement_between_stat_and_open(tmp_path, monkeypatch, replacement):
    source, destination = tmp_path / "source", tmp_path / "dest"
    source.mkdir()
    destination.mkdir()
    entry = source / "victim"
    outside = tmp_path / "outside"
    if replacement == "directory":
        entry.mkdir()
        outside.mkdir()
        (outside / "data").write_bytes(b"synthetic-outside-bytes")
    else:
        entry.write_text("safe")
        outside.write_bytes(b"synthetic-outside-bytes")
    original = os.open
    swapped = False

    def swap(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "victim" and not swapped:
            swapped = True
            entry.rename(source / "old")
            if replacement == "fifo":
                # Ensure the test itself cannot hang even if protection regresses.
                assert flags & os.O_NONBLOCK
                os.mkfifo(entry)
            else:
                entry.symlink_to(outside, target_is_directory=replacement == "directory")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap)
    with pytest.raises(SessionError):
        files.copy_tree(source, destination)
    assert swapped and not list(destination.iterdir())


def test_open_source_root_ancestor_stays_pinned(tmp_path, monkeypatch):
    parent, destination, outside = (tmp_path / name for name in ("parent", "dest", "outside"))
    source = parent / "source"
    source.mkdir(parents=True)
    destination.mkdir()
    (outside / "source").mkdir(parents=True)
    (source / "a").write_bytes(b"safe-first")
    (source / "z").write_bytes(b"safe-later")
    (outside / "source/z").write_bytes(b"synthetic-outside-bytes")
    original = shutil.copyfileobj
    swapped = False

    def swap(reader, writer, *args):
        nonlocal swapped
        if not swapped:
            swapped = True
            parent.rename(tmp_path / "old-parent")
            parent.symlink_to(outside, target_is_directory=True)
        return original(reader, writer, *args)

    monkeypatch.setattr(shutil, "copyfileobj", swap)
    with pytest.raises(SessionError, match="changed"):
        files.copy_tree(source, destination)
    assert (destination / "z").read_bytes() == b"safe-later"
