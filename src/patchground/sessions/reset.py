"""Restore ordinary workspace files without invoking Git or following links."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from contextlib import suppress
from pathlib import Path

from patchground.sessions import store
from patchground.sessions.files import copy_tree, excluded, open_directory, open_entry
from patchground.sessions.models import ResetResult, SessionError


def _inspect(parent: int) -> dict[str, object]:
    result: dict[str, object] = {}
    for name in sorted(os.listdir(parent)):
        if excluded(name):
            result[name] = None
            continue
        with open_entry(parent, name) as entry:
            result[name] = _inspect(entry) if stat.S_ISDIR(os.fstat(entry).st_mode) else False
    return result


def _protected(node: object) -> bool:
    return node is None or (isinstance(node, dict) and any(_protected(v) for v in node.values()))


def _preflight(original: dict[str, object], current: dict[str, object]) -> None:
    for name, node in original.items():
        if name not in current:
            continue
        target = current[name]
        if isinstance(node, dict) and isinstance(target, dict):
            _preflight(node, target)
        elif _protected(target):
            raise SessionError("reset blocked: starting files conflict with protected entries")


def _empty(parent: int) -> bool:
    return not os.listdir(parent)


def _clear(parent: int) -> None:
    for name in sorted(os.listdir(parent)):
        if excluded(name):
            continue
        directory = False
        with open_entry(parent, name) as entry:
            directory = stat.S_ISDIR(os.fstat(entry).st_mode)
            if directory:
                _clear(entry)
                empty = _empty(entry)
        if directory:
            if empty:
                os.rmdir(name, dir_fd=parent)
        else:
            os.unlink(name, dir_fd=parent)


def _restore(source: int, target: int) -> None:
    for name in sorted(os.listdir(source)):
        with open_entry(source, name) as entry:
            info = os.fstat(entry)
            if stat.S_ISDIR(info.st_mode):
                with suppress(FileExistsError):
                    os.mkdir(name, mode=0o700, dir_fd=target)
                with open_entry(target, name, os.O_RDONLY | os.O_DIRECTORY) as folder:
                    _restore(entry, folder)
            else:
                output = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=target,
                )
                with os.fdopen(output, "wb") as writer:
                    with os.fdopen(os.dup(entry), "rb") as reader:
                        shutil.copyfileobj(reader, writer)
                    os.fchmod(writer.fileno(), (stat.S_IMODE(info.st_mode) & 0o777) | 0o600)


def reset_session(session: Path | None = None, *, root: Path | None = None) -> ResetResult:
    """Reset a selected session; confirmation belongs to the CLI."""
    mutated = False
    try:
        root = (root if root is not None else store.default_root()).absolute()
        path = store.resolve(session, root)
        store.load(path)
        meta = path / ".session"
        with store.locked(meta):
            record, _, _ = store.load(path)
            from patchground.sessions.submission import require_active

            require_active(meta)
            with tempfile.TemporaryDirectory(
                prefix="patchground-reset-", dir=Path(tempfile.gettempdir()).resolve(strict=True)
            ) as temporary:
                staged = Path(temporary)
                copy_tree(meta / "original", staged)
                with open_directory(staged) as original, open_directory(path / "workspace") as work:
                    _preflight(_inspect(original), _inspect(work))
                    mutated = True
                    _clear(work)
                    _restore(original, work)
            store.append_event(meta, "reset", {})
            return ResetResult(
                session=path, workspace=path / "workspace", challenge_id=record.challenge_id
            )
    except (OSError, UnicodeError, SessionError) as exc:
        if mutated:
            raise SessionError(
                "reset incomplete: workspace may be partially restored; "
                "fix filesystem access and retry"
            ) from exc
        if isinstance(exc, SessionError):
            raise
        raise SessionError("reset unavailable: session storage could not be read") from exc
