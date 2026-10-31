"""Read exclusion data conservatively; never run Git against learner metadata."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from patchground.sessions.files import open_directory, open_entry
from patchground.sessions.git import resolve_executable
from patchground.sessions.models import SessionError


@dataclass(frozen=True)
class IgnoreRules:
    executable: str
    info: bytes
    global_rules: bytes
    ignore_case: bool


def _read(path: Path) -> bytes:
    """Missing files are empty; redirected, shared and special files are unavailable."""
    if path == Path(os.devnull):
        return b""
    with open_directory(Path(path.absolute().anchor)) as root:
        try:
            with ExitStack() as stack:
                parent = root
                for part in path.absolute().parts[1:-1]:
                    parent = stack.enter_context(
                        open_entry(parent, part, os.O_RDONLY | os.O_DIRECTORY)
                    )
                descriptor = stack.enter_context(open_entry(parent, path.name))
                info = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or info.st_size > 1024 * 1024
                ):
                    raise SessionError("unsafe exclusion data")
                with os.fdopen(os.dup(descriptor), "rb") as stream:
                    data = stream.read(1024 * 1024 + 1)
                after = os.fstat(descriptor)
                if len(data) > 1024 * 1024 or (
                    info.st_size,
                    info.st_mtime_ns,
                    info.st_ctime_ns,
                ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise SessionError("unsafe exclusion data")
                return data
        except FileNotFoundError:
            return b""


def resolve(
    workspace: Path, *, source: Path | None = None, inputs: tuple[Path, ...] = ()
) -> IgnoreRules | None:
    """Optional boundary: unsupported applicability never means an empty rule set."""
    try:
        return _resolve(workspace, source=source, inputs=inputs)
    except (Exception, KeyboardInterrupt):
        return None


def _resolve(
    workspace: Path, *, source: Path | None = None, inputs: tuple[Path, ...] = ()
) -> IgnoreRules:
    # Overrides that change repository discovery or inject command configuration cannot
    # be reproduced by this bounded resolver. In particular, never silently drop them.
    allowed = {"GIT_CONFIG_SYSTEM", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"}
    if any(name.startswith("GIT_") and name not in allowed for name in os.environ):
        raise SessionError("unsupported Git context")
    executable = resolve_executable(
        workspace,
        workspace.parent / ".session",
        *inputs,
        *((source,) if source is not None else ()),
    )
    # Only ordinary standalone repositories are supported. Gitfiles, linked worktrees,
    # missing metadata and alternate worktree roots require unavailable history.
    for folder in (workspace / ".git", workspace / ".git/objects", workspace / ".git/refs"):
        with open_directory(folder):
            pass
    if _read(workspace / ".git/commondir") or _read(workspace / ".git/config.worktree"):
        raise SessionError("unsupported worktree context")
    local = _read(workspace / ".git/config")
    if not local or not _read(workspace / ".git/HEAD"):
        raise SessionError("Git context unavailable")
    home = Path(os.environ.get("HOME", ""))
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
    if not home.is_absolute() or not xdg.is_absolute():
        raise SessionError("unsupported configuration path")
    with tempfile.TemporaryDirectory(prefix="patchground-ignore-config-") as temporary:
        private = Path(temporary)
        env = {
            "PATH": os.defpath,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(xdg),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "",
            "LC_ALL": "C",
        }
        repository = private / "repository"
        repository.mkdir()
        (repository / "objects").mkdir()
        (repository / "refs").mkdir()
        (repository / "HEAD").write_bytes(b"ref: refs/heads/unused\n")
        (repository / "config").write_bytes(b"[core]\n bare = true\n")
        command = [
            executable,
            "--git-dir=" + str(repository),
            "--no-pager",
            "--no-optional-locks",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.attributesFile=" + os.devnull,
            "-c",
            "protocol.allow=never",
        ]

        def run(args: list[str], *, environment: dict[str, str] = env, data: bytes = b"") -> bytes:
            result = subprocess.run(
                [*command, *args],
                cwd=private,
                env=environment,
                input=data,
                capture_output=True,
                timeout=10,
                check=True,
            )
            return result.stdout

        configs: list[bytes] = []
        no_system = os.environ.get("GIT_CONFIG_NOSYSTEM", "0").lower()
        if no_system not in ("1", "true", "yes", "on", "0", "false", "no", "off"):
            raise SessionError("unsupported system configuration override")
        if no_system in ("0", "false", "no", "off"):
            system = os.environ.get("GIT_CONFIG_SYSTEM")
            if system is None:
                # Git exposes its compiled-in path. This read-only data query may read
                # system configuration, but cannot invoke hooks, filters or tools.
                discovery = dict(env)
                discovery.pop("GIT_CONFIG_SYSTEM")
                discovery.pop("GIT_CONFIG_NOSYSTEM")
                system = os.fsdecode(
                    run(["var", "GIT_CONFIG_SYSTEM"], environment=discovery)
                ).removesuffix("\n")
            path = Path(system)
            if not path.is_absolute():
                raise SessionError("unsupported system configuration path")
            configs.append(_read(path))
        if "GIT_CONFIG_GLOBAL" in os.environ:
            path = Path(os.environ["GIT_CONFIG_GLOBAL"])
            if not path.is_absolute():
                raise SessionError("unsupported global configuration path")
            configs.append(_read(path))
        else:
            configs.extend((_read(xdg / "git/config"), _read(home / ".gitconfig")))
        configs.append(local)
        excludes: bytes | None = None
        ignore_case = False
        for data in configs:
            pairs = run(["config", "--no-includes", "--file", "-", "--null", "--list"], data=data)
            for pair in pairs.split(b"\0"):
                if not pair:
                    continue
                key = pair.partition(b"\n")[0]
                if (
                    key.startswith((b"include.", b"includeif.", b"extensions."))
                    or key == b"core.worktree"
                ):
                    raise SessionError("unsupported configuration applicability")
                if key == b"core.excludesfile":
                    # Ask Git to expand its path syntax, then copy only validated data.
                    expanded = run(
                        [
                            "config",
                            "--no-includes",
                            "--file",
                            "-",
                            "--path",
                            "--null",
                            "--get",
                            "core.excludesFile",
                        ],
                        data=data,
                    ).removesuffix(b"\0")
                    if expanded:
                        path = Path(os.fsdecode(expanded))
                        if not path.is_absolute():
                            raise SessionError("relative exclusion path unavailable")
                        excludes = _read(path)
                    else:
                        excludes = b""
                elif key == b"core.ignorecase":
                    parsed = run(
                        [
                            "config",
                            "--no-includes",
                            "--file",
                            "-",
                            "--bool",
                            "--get",
                            "core.ignoreCase",
                        ],
                        data=data,
                    )
                    ignore_case = parsed.strip() == b"true"
        return IgnoreRules(
            executable=executable,
            info=_read(workspace / ".git/info/exclude"),
            global_rules=_read(xdg / "git/ignore") if excludes is None else excludes,
            ignore_case=ignore_case,
        )
