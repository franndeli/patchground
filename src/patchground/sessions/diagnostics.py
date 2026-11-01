"""Read-only readiness probes for `doctor`: Git availability and session-disk space.

Never touches an existing workspace or runs a challenge; Git uses a temporary clean directory.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from patchground.sessions.models import SessionError
from patchground.sessions.store import SESSIONS_ENV
from patchground.sessions.workflow import _root

MINIMUM_FREE_BYTES = 1024**3
_GIT_TIMEOUT = 10.0
_VERSION = re.compile(r"git version (\d+(?:\.\d+){1,3})")


class GitProblem(StrEnum):
    MISSING = "missing"  # no git on PATH
    UNUSABLE = "unusable"  # found, but failed, timed out or printed no recognisable version


@dataclass(frozen=True)
class GitProbe:
    available: bool
    problem: GitProblem | None = None
    version: str | None = None


class DiskProblem(StrEnum):
    LOW_SPACE = "low_space"
    NOT_WRITABLE = "not_writable"
    UNREADABLE = "unreadable"  # no existing ancestor could be inspected
    INVALID_SETTING = "invalid_setting"  # PATCHGROUND_SESSIONS_DIR is not an absolute path


@dataclass(frozen=True)
class DiskProbe:
    """Space where sessions are created. ``location`` is display-safe (home shown as ``~``)."""

    ok: bool
    location: str
    problem: DiskProblem | None = None
    free_bytes: int | None = None
    minimum_bytes: int = MINIMUM_FREE_BYTES


def probe_git() -> GitProbe:
    """Run ``git --version`` with no user/system configuration and a bounded wait."""
    executable = shutil.which("git")
    if executable is None:
        return GitProbe(available=False, problem=GitProblem.MISSING)
    try:
        resolved = str(Path(executable).resolve(strict=True))
        with tempfile.TemporaryDirectory(prefix="patchground-doctor-") as home:
            env = {
                "PATH": os.defpath,
                "HOME": home,
                "XDG_CONFIG_HOME": home,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "LC_ALL": "C",
            }
            completed = subprocess.run(
                [resolved, "--version"],
                cwd=home,
                env=env,
                check=True,
                capture_output=True,
                timeout=_GIT_TIMEOUT,
            )
    except (OSError, subprocess.SubprocessError):
        return GitProbe(available=False, problem=GitProblem.UNUSABLE)
    match = _VERSION.search(completed.stdout.decode("ascii", errors="replace"))
    if match is None:
        return GitProbe(available=False, problem=GitProblem.UNUSABLE)
    return GitProbe(available=True, version=match.group(1))


def probe_disk(root: Path | None = None, *, minimum_bytes: int = MINIMUM_FREE_BYTES) -> DiskProbe:
    """Check free space and writability at the sessions root, or its nearest existing ancestor."""
    try:
        target = _root(root)
    except SessionError:
        return DiskProbe(ok=False, location=SESSIONS_ENV, problem=DiskProblem.INVALID_SETTING)
    location = display_path(target)
    existing = _nearest_existing(target)
    if existing is None:
        return DiskProbe(ok=False, location=location, problem=DiskProblem.UNREADABLE)
    if not existing.is_dir():  # a file where a directory is needed
        return DiskProbe(ok=False, location=location, problem=DiskProblem.NOT_WRITABLE)
    try:
        free = shutil.disk_usage(existing).free
    except OSError:
        return DiskProbe(ok=False, location=location, problem=DiskProblem.UNREADABLE)
    if not os.access(existing, os.W_OK | os.X_OK):
        return DiskProbe(
            ok=False,
            location=location,
            problem=DiskProblem.NOT_WRITABLE,
            free_bytes=free,
            minimum_bytes=minimum_bytes,
        )
    if free < minimum_bytes:
        return DiskProbe(
            ok=False,
            location=location,
            problem=DiskProblem.LOW_SPACE,
            free_bytes=free,
            minimum_bytes=minimum_bytes,
        )
    return DiskProbe(ok=True, location=location, free_bytes=free, minimum_bytes=minimum_bytes)


def _nearest_existing(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        try:
            if candidate.exists():
                return candidate
        except OSError:
            return None
    return None


def display_path(path: Path) -> str:
    """Show paths under the user's home as ``~/...`` so output never reveals the home path."""
    try:
        home = Path.home().absolute()
    except (RuntimeError, KeyError):
        return str(path)
    try:
        relative = path.relative_to(home)
    except ValueError:
        return str(path)
    return "~" if relative == Path() else str(Path("~") / relative)
