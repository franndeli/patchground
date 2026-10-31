"""Shared descriptor-safe local access and non-executing Git executable selection."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path


class SafetyError(Exception):
    """A local resource cannot be accessed safely."""


def no_links(
    path: Path, *, error: type[Exception] = SafetyError, label: str = "filesystem"
) -> None:
    """Check ancestors even when the destination does not exist yet."""
    for entry in (*reversed(path.absolute().parents), path.absolute()):
        if entry.is_symlink():
            raise error(f"{label} paths must not contain symlinks")


def safe_path(
    path: Path, *, directory: bool, error: type[Exception] = SafetyError, label: str = "filesystem"
) -> None:
    """Reject redirected ancestors as well as redirected leaf entries."""
    no_links(path, error=error, label=label)
    mode = path.lstat().st_mode
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        raise error(f"{label} path has an invalid file type")


@contextmanager
def open_directory(
    path: Path, *, error: type[Exception] = SafetyError, label: str = "filesystem"
) -> Iterator[int]:
    """Pin every ancestor, not just the leaf, without following any links."""
    root = os.open(path.absolute().anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with ExitStack() as ancestors:
            descriptor = root
            for part in path.absolute().parts[1:]:
                descriptor = ancestors.enter_context(
                    open_entry(
                        descriptor, part, os.O_RDONLY | os.O_DIRECTORY, error=error, label=label
                    )
                )
            yield descriptor
    except OSError as exc:
        raise error(f"{label} directory contains a symlink or is unavailable") from exc
    finally:
        os.close(root)


@contextmanager
def open_entry(
    parent: int,
    name: str,
    flags: int = os.O_RDONLY,
    *,
    error: type[Exception] = SafetyError,
    label: str = "filesystem",
) -> Iterator[int]:
    """Validate the opened inode; NONBLOCK prevents a raced-in FIFO from hanging."""
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not (stat.S_ISDIR(before.st_mode) or stat.S_ISREG(before.st_mode)):
        raise error(f"{label} tree contains a symlink or special file")
    try:
        descriptor = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except OSError as exc:
        raise error(f"{label} tree contains a symlink or special file or changed") from exc
    try:
        actual = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (actual.st_dev, actual.st_ino) or not (
            stat.S_ISDIR(actual.st_mode) or stat.S_ISREG(actual.st_mode)
        ):
            raise error(f"{label} tree changed during access")
        yield descriptor
        after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (actual.st_dev, actual.st_ino) != (after.st_dev, after.st_ino):
            raise error(f"{label} tree changed during access")
    finally:
        os.close(descriptor)


def resolve_git(*inputs: Path, error: type[Exception] = SafetyError) -> str:
    """Trust only absolute PATH candidates outside cwd and all supplied input trees.

    PATH is an installation search policy, not proof of executable provenance. Never
    probe a candidate by running it. Canonicalize both the search path and target so
    symlinks cannot disguise challenge input as an installed Git executable.
    """
    try:
        roots: list[Path] = []
        for path in (Path.cwd(), *inputs):
            roots.extend((path.absolute(), path.resolve(strict=False)))
        for directory in os.environ.get("PATH", os.defpath).split(os.pathsep):
            if not Path(directory).is_absolute():
                continue
            candidate = Path(directory) / "git"
            if any(candidate.is_relative_to(root) for root in roots):
                continue
            try:
                executable = candidate.resolve(strict=True)
                if any(executable.is_relative_to(root) for root in roots):
                    continue
                if stat.S_ISREG(executable.stat().st_mode) and os.access(executable, os.X_OK):
                    return str(executable)
            except (OSError, RuntimeError):
                continue
    except (OSError, RuntimeError):
        pass
    raise error("safe Git executable unavailable")
