"""The sole Git write: initialize a fresh baseline before handing it to the user."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from patchground.sessions.models import SessionError


def initialize(workspace: Path) -> None:
    if (workspace / ".git").exists():
        raise SessionError("refusing to reuse an existing repository")
    executable = shutil.which("git")
    if executable is None:
        raise SessionError("git is required to start a session")
    # which() may return a relative PATH entry; bind it before changing cwd.
    executable = str(Path(executable).resolve(strict=True))
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
