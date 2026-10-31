"""Import raw Git objects through isolated metadata, never a source checkout."""

from __future__ import annotations

import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from patchground import safeio
from patchground.packs.models import PackError, SourceSnapshot

MAX_BYTES = 100 * 1024 * 1024
MAX_FILES = 10_000
TIMEOUT = 300


def _run_process(
    command: list[str], *, cwd: Path, env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess[bytes]:
    """Cancel Git and its HTTPS helpers together on timeout or interruption."""
    with subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    ) as process:
        try:
            stdout, _ = process.communicate(timeout=timeout)
        except BaseException:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout)


def _source(source: str | Path) -> tuple[str, Literal["https", "local"], Path | None]:
    value = str(source)
    if "://" in value or value.startswith(("git@", "ssh:", "file:")):
        try:
            url = urlsplit(value)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
                or "%" in url.netloc
                or any(c.isspace() for c in value)
            ):
                raise ValueError
            port = url.port
            host = url.hostname.lower()
            if ":" in host:
                host = f"[{host}]"
            netloc = host + (f":{port}" if port and port != 443 else "")
            return urlunsplit(("https", netloc, url.path.rstrip("/"), "", "")), "https", None
        except ValueError:
            raise PackError("pack source must be public HTTPS without credentials") from None
    path = Path(value).absolute()
    safeio.no_links(path, error=PackError, label="pack source")
    return str(path.resolve()), "local", path


def _copy_tree(parent: int, name: str, destination: Path, deadline: float) -> None:
    if time.monotonic() > deadline:
        raise PackError("pack transport timed out")
    with safeio.open_entry(parent, name, error=PackError, label="Git data") as fd:
        mode = os.fstat(fd).st_mode
        if stat.S_ISDIR(mode):
            destination.mkdir()
            for child in os.listdir(fd):  # noqa: PTH208 - descriptor-pinned listing
                # Alternates and commit graphs are unnecessary and may reference outside data.
                if destination.name == "objects" and child == "info":
                    continue
                _copy_tree(fd, child, destination / child, deadline)
        else:
            with destination.open("xb") as output:
                while data := os.read(fd, 1024 * 1024):
                    if time.monotonic() > deadline:
                        raise PackError("pack transport timed out")
                    output.write(data)


@contextmanager
def fetch_pack(source: str | Path, ref: str = "HEAD") -> Iterator[SourceSnapshot]:
    """Yield a private, temporary exact-commit regular-file tree with provenance."""
    try:
        canonical, kind, local = _source(source)
        if not ref or ref.startswith("-") or any(c in ref for c in "\x00\r\n"):
            raise PackError("invalid pack revision")
        git = safeio.resolve_git(*((local,) if local else ()), error=PackError)
        deadline = time.monotonic() + TIMEOUT
        with tempfile.TemporaryDirectory(prefix="patchground-source-") as temporary:
            root = Path(temporary)
            metadata = root / "repo"
            home = root / "home"
            home.mkdir()
            env = {
                "PATH": str(Path(git).parent) + os.pathsep + os.defpath,
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home),
                "LC_ALL": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_ALLOW_PROTOCOL": "https",
                "GIT_ATTR_NOSYSTEM": "1",
            }

            def run(*args: str) -> bytes:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PackError("pack transport timed out")
                result = _run_process(
                    [
                        git,
                        "-c",
                        "core.hooksPath=/dev/null",
                        "-c",
                        "credential.helper=",
                        "-c",
                        "http.followRedirects=false",
                        "-c",
                        "gc.auto=0",
                        "-c",
                        "maintenance.auto=false",
                        "--git-dir",
                        str(metadata),
                        *args,
                    ],
                    cwd=root,
                    env=env,
                    timeout=remaining,
                )
                if result.returncode:
                    raise PackError("cannot read pack source or revision")
                return result.stdout

            if local is not None:
                safeio.safe_path(local, directory=True, error=PackError, label="pack source")
                source_git = local / ".git" if (local / ".git").exists() else local
                with safeio.open_directory(source_git, error=PackError, label="Git data") as fd:
                    object_format = "sha1"
                    with safeio.open_entry(fd, "config", error=PackError) as config:
                        config_data = os.read(config, 1024 * 1024 + 1)
                    if len(config_data) > 1024 * 1024:
                        raise PackError("Git configuration is too large")
                    if re.search(rb"^\s*objectformat\s*=\s*sha256\s*$", config_data, re.M | re.I):
                        object_format = "sha256"
                    run("init", "--bare", f"--object-format={object_format}", "--template=")
                    for name in ("objects", "refs", "HEAD", "packed-refs", "shallow"):
                        if name not in os.listdir(fd):  # noqa: PTH208 - descriptor-pinned listing
                            continue
                        target = metadata / name
                        if target.is_dir():
                            shutil.rmtree(target)
                        elif target.exists():
                            target.unlink()
                        _copy_tree(fd, name, target, deadline)
                revision = ref
            else:
                run("init", "--bare", "--template=")
                run("fetch", "--no-tags", "--no-recurse-submodules", "--depth=1", canonical, ref)
                revision = "FETCH_HEAD"
            commit = run(
                "rev-parse", "--verify", "--end-of-options", revision + "^{commit}"
            ).strip()
            if not re.fullmatch(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
                raise PackError("invalid pack commit")
            # Git normally trusts loose-object names; verify hashes before provenance is asserted.
            run("fsck", "--full", "--no-reflogs", "--no-dangling", commit.decode())
            entries = run("ls-tree", "-r", "-l", "-z", commit.decode()).split(b"\0")
            files: list[tuple[Path, str, int, bool]] = []
            total = 0
            for entry in entries:
                if not entry:
                    continue
                header, raw_path = entry.split(b"\t", 1)
                mode, obj_type, oid, size = header.split()
                parts = raw_path.decode("utf-8").split("/")
                if (
                    mode not in (b"100644", b"100755")
                    or obj_type != b"blob"
                    or any(
                        p in ("", ".", "..") or p.lower() == ".git" or "\\" in p or ":" in p
                        for p in parts
                    )
                ):
                    raise PackError("pack contains an unsupported or unsafe Git entry")
                length = int(size)
                total += length
                files.append((Path(*parts), oid.decode(), length, mode == b"100755"))
                if total > MAX_BYTES or len(files) > MAX_FILES:
                    raise PackError("pack exceeds exported size or file limit")
            tree = root / "tree"
            tree.mkdir()
            for relative, blob_id, length, executable in files:
                data = run("cat-file", "blob", blob_id)
                if len(data) != length:
                    raise PackError("pack blob changed during retrieval")
                if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
                    raise PackError("Git LFS content is unsupported")
                target = tree / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(0o755 if executable else 0o644)
            yield SourceSnapshot(
                path=tree, source=canonical, source_kind=kind, commit=commit.decode()
            )
    except PackError:
        raise
    except subprocess.TimeoutExpired:
        raise PackError("pack transport timed out") from None
    except (OSError, ValueError, UnicodeError, RuntimeError):
        raise PackError("cannot safely retrieve pack source") from None
