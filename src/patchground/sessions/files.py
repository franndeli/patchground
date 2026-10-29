"""Bounded copies: no links, special files, Git metadata or credential files."""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager, suppress
from fnmatch import fnmatch
from pathlib import Path

from patchground.sessions.models import SessionError


def excluded(name: str) -> bool:
    return name.lower() == ".git" or any(
        fnmatch(name.lower(), pattern) for pattern in (".env*", "*.pem", "*.key", "id_*")
    )


def no_links(path: Path) -> None:
    """Check ancestors even when the destination does not exist yet."""
    for entry in (*reversed(path.absolute().parents), path.absolute()):
        if entry.is_symlink():
            raise SessionError("session paths must not contain symlinks")


def safe_path(path: Path, *, directory: bool) -> None:
    """Reject redirected ancestors as well as redirected leaf entries."""
    no_links(path)
    mode = path.lstat().st_mode
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        raise SessionError("session path has an invalid file type")


@contextmanager
def open_directory(path: Path) -> Iterator[int]:
    """Pin every ancestor, not just the leaf, without following any links."""
    root = os.open(path.absolute().anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with ExitStack() as ancestors:
            descriptor = root
            for part in path.absolute().parts[1:]:
                descriptor = ancestors.enter_context(
                    open_entry(descriptor, part, os.O_RDONLY | os.O_DIRECTORY)
                )
            yield descriptor
    except OSError as exc:
        raise SessionError("session directory contains a symlink or is unavailable") from exc
    finally:
        os.close(root)


@contextmanager
def open_entry(parent: int, name: str, flags: int = os.O_RDONLY) -> Iterator[int]:
    """Validate the opened inode; NONBLOCK prevents a raced-in FIFO from hanging."""
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not (stat.S_ISDIR(before.st_mode) or stat.S_ISREG(before.st_mode)):
        raise SessionError("session tree contains a symlink or special file")
    try:
        descriptor = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except OSError as exc:
        raise SessionError("session tree contains a symlink or special file or changed") from exc
    try:
        actual = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (actual.st_dev, actual.st_ino) or not (
            stat.S_ISDIR(actual.st_mode) or stat.S_ISREG(actual.st_mode)
        ):
            raise SessionError("session tree changed during access")
        yield descriptor
        after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (actual.st_dev, actual.st_ino) != (after.st_dev, after.st_ino):
            raise SessionError("session tree changed during access")
    finally:
        os.close(descriptor)


def tree(path: Path, *, skip: bool = False) -> list[Path]:
    entries: list[Path] = []

    def visit(parent: int, base: Path) -> None:
        for name in sorted(os.listdir(parent)):
            with open_entry(parent, name) as descriptor:
                if skip and excluded(name):
                    continue
                entry = base / name
                entries.append(entry)
                if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    visit(descriptor, entry)

    with open_directory(path) as descriptor:
        visit(descriptor, path)
    return entries


def copy_tree(source: Path, destination: Path) -> None:
    def copy(parent: int, target: int) -> None:
        for name in sorted(os.listdir(parent)):
            with open_entry(parent, name) as descriptor:
                info = os.fstat(descriptor)
                if excluded(name):
                    continue
                if stat.S_ISDIR(info.st_mode):
                    with suppress(FileExistsError):
                        os.mkdir(name, mode=0o700, dir_fd=target)
                    # Layers may merge directories, but never follow destination links.
                    with open_entry(target, name) as folder:
                        if not stat.S_ISDIR(os.fstat(folder).st_mode):
                            raise SessionError("check layer collision")
                        copy(descriptor, folder)
                else:
                    try:
                        output = os.open(
                            name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600,
                            dir_fd=target,
                        )
                    except FileExistsError as exc:
                        raise SessionError("check layer collision") from exc
                    with os.fdopen(output, "wb") as writer:
                        # dup owns only the stream lifetime; no pathname is reopened.
                        with os.fdopen(os.dup(descriptor), "rb") as reader:
                            shutil.copyfileobj(reader, writer)
                        os.fchmod(writer.fileno(), stat.S_IMODE(info.st_mode) & 0o777)

    with open_directory(source) as source_fd, open_directory(destination) as destination_fd:
        copy(source_fd, destination_fd)


def readonly(path: Path) -> None:
    def visit(parent: int) -> None:
        for name in os.listdir(parent):
            with open_entry(parent, name) as descriptor:
                mode = os.fstat(descriptor).st_mode
                if stat.S_ISDIR(mode):
                    visit(descriptor)
                os.fchmod(descriptor, 0o500 if stat.S_ISDIR(mode) or mode & 0o111 else 0o400)

    with open_directory(path) as descriptor:
        visit(descriptor)
        os.fchmod(descriptor, 0o500)


def remove_partial(path: Path) -> None:
    # Only called for a newly reserved directory, never an existing attempt.
    for base, dirs, _files in os.walk(path, followlinks=False):
        Path(base).chmod(0o700)
        for name in dirs:
            entry = Path(base) / name
            if not entry.is_symlink():
                entry.chmod(0o700)
    shutil.rmtree(path)
