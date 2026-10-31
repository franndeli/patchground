"""Bounded copies: no links, special files, Git metadata or credential files."""

from __future__ import annotations

import os
import shutil
import stat
from contextlib import AbstractContextManager, suppress
from fnmatch import fnmatch
from pathlib import Path

from patchground import safeio
from patchground.sessions.models import SessionError


def excluded(name: str) -> bool:
    return name.lower() == ".git" or any(
        fnmatch(name.lower(), pattern) for pattern in (".env*", "*.pem", "*.key", "id_*")
    )


def no_links(path: Path) -> None:
    safeio.no_links(path, error=SessionError, label="session")


def safe_path(path: Path, *, directory: bool) -> None:
    safeio.safe_path(path, directory=directory, error=SessionError, label="session")


def open_directory(path: Path) -> AbstractContextManager[int]:
    return safeio.open_directory(path, error=SessionError, label="session")


def open_entry(parent: int, name: str, flags: int = os.O_RDONLY) -> AbstractContextManager[int]:
    return safeio.open_entry(parent, name, flags, error=SessionError, label="session")


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
