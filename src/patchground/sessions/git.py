"""Initialize fresh workspace Git before handoff; private checkpoints live in history."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path

from patchground.sessions.models import SessionError


def resolve_executable(*inputs: Path) -> str:
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
    raise SessionError("safe Git executable unavailable")


def initialize(workspace: Path, *, source: Path | None = None) -> None:
    if (workspace / ".git").exists():
        raise SessionError("refusing to reuse an existing repository")
    executable = resolve_executable(workspace, *((source,) if source is not None else ()))
    with tempfile.TemporaryDirectory(prefix="patchground-git-") as home:
        # Allowlist, not a GIT_* denylist: config, index, object stores, hooks and
        # process injection settings must not be inherited from the caller.
        env = {
            "PATH": os.defpath,
            "HOME": home,
            "XDG_CONFIG_HOME": home,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
        command = [
            executable,
            "-c",
            "core.hooksPath=" + os.devnull,
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.attributesFile=" + os.devnull,
            "-c",
            "core.autocrlf=false",
            "-c",
            "commit.gpgSign=false",
            "-c",
            "user.name=Patchground",
            "-c",
            "user.email=0+patchground@users.noreply.github.com",
        ]
        for args in (
            ["init", "--template=", "--initial-branch=main"],
            ["add", "--all", "--", "."],
            ["commit", "--allow-empty", "-m", "Initial challenge workspace"],
        ):
            try:
                subprocess.run(
                    [*command, *args],
                    cwd=workspace,
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise SessionError("could not initialize the fresh Git baseline") from exc
