"""Private pack state: catalog, managed cache layout, locking and verified tree capture.

Everything under the state directory is data. Metadata is validated strictly on every read and
never repaired silently; cache paths are derived from validated names and commits, never stored.
Trees are copied through descriptor-pinned ``safeio`` primitives while being hashed, so the bytes
that were reviewed are the bytes that are kept or executed.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import stat
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from patchground.packs.discovery import ChallengeSummary
from patchground.packs.models import PackError, PackIdentity
from patchground.safeio import SafetyError, open_directory, open_entry, safe_path
from patchground.spec.models import SemVer, Slug

REGISTRY_FILE = "registry.json"
LOCK_FILE = ".lock"
PACKS_DIR = "packs"
MAX_FILES = 10_000
MAX_BYTES = 100 * 1024 * 1024
MAX_STATE_BYTES = 8 * 1024 * 1024
_COMMIT = r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$"
_CHUNK = 1024 * 1024


def _error(message: str) -> PackError:
    return PackError(message)


def state_root(root: Path | None) -> Path:
    """Canonical state directory. Resolving here is the one trusted step; nothing below may link."""
    base = Path(root) if root is not None else Path("~/.patchground")
    return base.expanduser().absolute().resolve()


def packs_dir(root: Path) -> Path:
    return root / PACKS_DIR


def cache_path(root: Path, name: str, commit: str) -> Path:
    return packs_dir(root) / f"{name}@{commit}"


def make_identity(name: str, version: str, kind: str, source: str, commit: str, digest: str) -> str:
    payload = json.dumps([name, version, kind, source, commit, digest], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Version(_Model):
    version: SemVer
    commit: str = Field(pattern=_COMMIT)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    consented: bool = False
    challenges: tuple[ChallengeSummary, ...]
    folders: dict[str, str]
    """Per-challenge content digest, so updates can report changed challenges."""


class Entry(_Model):
    source: str = Field(min_length=1, max_length=4096)
    source_kind: Literal["https", "local"]
    ref: str = Field(min_length=1, max_length=256, pattern=r"^[^\x00-\x1f\x7f]+$")
    active: str = Field(pattern=_COMMIT)
    versions: dict[str, Version]


class State(_Model):
    format: Literal[1] = 1
    packs: dict[Slug, Entry] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self) -> State:
        for name, entry in self.packs.items():
            _check_source(entry.source_kind, entry.source)
            if entry.active not in entry.versions:
                raise ValueError("active version is not registered")
            for commit, ver in entry.versions.items():
                expected = make_identity(
                    name, ver.version, entry.source_kind, entry.source, commit, ver.digest
                )
                if ver.commit != commit or ver.identity != expected:
                    raise ValueError("version identity does not match its record")
                names = [summary.id for summary in ver.challenges]
                if len(set(names)) != len(names) or set(names) != set(ver.folders):
                    raise ValueError("challenge index is inconsistent")
        return self


def _check_source(kind: str, source: str) -> None:
    if "\x00" in source:
        raise ValueError("unsafe source")
    if kind == "local":
        if not Path(source).is_absolute():
            raise ValueError("local source must be absolute")
        return
    parts = urlsplit(source)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("source must be a credential-free HTTPS URL")


def identity_of(name: str, entry: Entry, ver: Version) -> PackIdentity:
    return PackIdentity(
        name=name,
        version=ver.version,
        source=entry.source,
        source_kind=entry.source_kind,
        commit=ver.commit,
        digest=ver.digest,
        identity=ver.identity,
    )


def load_state(root: Path) -> State:
    """Read the catalog without creating anything; missing state is simply empty."""
    path = root / REGISTRY_FILE
    try:
        path.lstat()
    except FileNotFoundError:
        return State()
    except OSError as exc:
        raise _error("pack registry is unavailable") from exc
    try:
        safe_path(path, directory=False, error=PackError, label="pack registry")
        with (
            open_directory(path.parent, error=PackError, label="pack registry") as parent,
            open_entry(parent, path.name, error=PackError, label="pack registry") as fd,
        ):
            data = _read_all(fd, MAX_STATE_BYTES)
        return State.model_validate_json(data)
    except (OSError, ValueError, SafetyError, PackError) as exc:
        raise _error("pack registry is corrupt or unsafe") from exc


def _read_all(fd: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(_CHUNK, limit + 1 - total))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise _error("file exceeds its size limit")


def read_limited(path: Path, limit: int) -> bytes:
    """Read one regular file through pinned descriptors; oversize is an error, never truncation."""
    safe_path(path, directory=False, error=PackError, label="pack")
    with (
        open_directory(path.parent, error=PackError, label="pack") as parent,
        open_entry(parent, path.name, error=PackError, label="pack") as fd,
    ):
        return _read_all(fd, limit)


def ensure_dirs(root: Path) -> None:
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        packs_dir(root).mkdir(exist_ok=True, mode=0o700)
        safe_path(root, directory=True, error=PackError, label="pack state")
        safe_path(packs_dir(root), directory=True, error=PackError, label="pack state")
    except OSError as exc:
        raise _error("pack state directory cannot be prepared") from exc


@contextmanager
def locked(root: Path) -> Iterator[None]:
    """Exclusive cross-process lock for every state mutation; initializes the state directory."""
    ensure_dirs(root)
    try:
        fd = os.open(root / LOCK_FILE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise _error("pack state lock is unavailable") from exc
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


class PublishedStateError(PackError):
    """Catalog publication happened; deleting its newly referenced cache would corrupt state."""


def save_state(root: Path, state: State) -> None:
    """Publish through a pinned directory; distinguish pre- and post-publication failures."""
    data = state.model_dump_json(indent=2).encode()
    if len(data) > MAX_STATE_BYTES:
        raise PackError("pack registry would exceed its size limit; state was not changed")
    tmp = f".registry-{os.getpid()}-{secrets.token_hex(6)}.tmp"
    published = False
    try:
        with open_directory(root, error=PackError, label="pack state") as directory:
            created = False
            try:
                fd = os.open(
                    tmp,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory,
                )
                created = True
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, REGISTRY_FILE, src_dir_fd=directory, dst_dir_fd=directory)
                published = True
                os.fsync(directory)
            finally:
                if created and not published:
                    with suppress(OSError):
                        os.unlink(tmp, dir_fd=directory)
    except (OSError, PackError) as exc:
        if published:
            raise PublishedStateError(
                "pack state was published but durability could not be confirmed; "
                "inspect pack list before retrying; cached files may remain"
            ) from exc
        raise PackError("pack registry could not be written") from exc


@dataclass(frozen=True)
class Capture:
    digest: str
    files: Mapping[str, str]
    """Relative path -> file executable flag/content digest or a directory marker."""

    def folder_digests(self, names: tuple[str, ...]) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in names:
            h = hashlib.sha256()
            for rel, value in sorted(self.files.items()):
                if rel.startswith(f"{name}/"):
                    h.update(f"{rel}\n{value}\n".encode())
            result[name] = h.hexdigest()
        return result


def capture_tree(source: Path, destination: Path | None, *, seal: bool) -> Capture:
    """Hash regular files and directories while optionally copying exactly the bytes read.

    ``destination`` must be an existing empty directory, or ``None`` to only verify (the digest is
    the same either way). ``seal`` makes a copy read-only (cache); otherwise it is private and
    owner-writable (execution copy). Symlinks, special files, racing replacements and over-limit
    trees fail with a safe error.
    """
    files: dict[str, str] = {}
    file_count = 0
    total = 0

    def copy(parent: int, target: int | None, prefix: str) -> None:
        nonlocal total, file_count
        for name in sorted(os.listdir(parent)):
            rel = f"{prefix}{name}"
            with open_entry(parent, name, error=PackError, label="pack") as fd:
                info = os.fstat(fd)
                if stat.S_ISDIR(info.st_mode):
                    files[f"{rel}/"] = "d"
                    if target is None:
                        copy(fd, None, f"{rel}/")
                        continue
                    os.mkdir(name, mode=0o700, dir_fd=target)
                    with open_entry(
                        target, name, os.O_RDONLY | os.O_DIRECTORY, error=PackError, label="pack"
                    ) as child:
                        copy(fd, child, f"{rel}/")
                        os.fchmod(child, 0o555 if seal else 0o700)
                        if seal:
                            os.fsync(child)
                    continue
                if file_count >= MAX_FILES:
                    raise _error("pack exceeds the file count limit")
                file_count += 1
                executable = bool(info.st_mode & 0o111)
                digest = hashlib.sha256()
                writer = None
                if target is not None:
                    output = os.open(
                        name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=target,
                    )
                    writer = os.fdopen(output, "wb")
                try:
                    while chunk := os.read(fd, _CHUNK):
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise _error("pack exceeds the size limit")
                        digest.update(chunk)
                        if writer is not None:
                            writer.write(chunk)
                    if writer is not None:
                        mode = (
                            (0o555 if executable else 0o444)
                            if seal
                            else (0o700 if executable else 0o600)
                        )
                        os.fchmod(writer.fileno(), mode)
                        if seal:
                            writer.flush()
                            os.fsync(writer.fileno())
                finally:
                    if writer is not None:
                        writer.close()
                files[rel] = f"{'x' if executable else '-'}{digest.hexdigest()}"

    try:
        with ExitStack() as stack:
            source_fd = stack.enter_context(open_directory(source, error=PackError, label="pack"))
            target_fd = (
                stack.enter_context(open_directory(destination, error=PackError, label="pack"))
                if destination is not None
                else None
            )
            copy(source_fd, target_fd, "")
            if target_fd is not None:
                os.fchmod(target_fd, 0o555 if seal else 0o700)
                if seal:
                    os.fsync(target_fd)
    except OSError as exc:
        raise _error("pack tree cannot be read or copied safely") from exc
    overall = hashlib.sha256()
    for rel in sorted(files):
        encoded = rel.encode()
        overall.update(len(encoded).to_bytes(8, "big") + encoded + files[rel].encode())
    return Capture(overall.hexdigest(), files)


def cache_problem(root: Path, name: str, ver: Version) -> str | None:
    """Why a registered cache directory cannot be trusted (None when bytes match the catalog)."""
    path = cache_path(root, name, ver.commit)
    try:
        safe_path(path, directory=True, error=PackError, label="installed pack")
        actual = capture_tree(path, None, seal=False).digest
    except (OSError, PackError):
        return "installed pack content is missing or unsafe"
    return None if actual == ver.digest else "installed pack content failed integrity verification"


@contextmanager
def hold_stage(path: Path) -> Iterator[tuple[int, int]]:
    """Keep stage ownership live through cleanup; see packs/SPEC.md for identity rules."""
    try:
        with open_directory(path.parent, error=PackError, label="pack state") as parent:
            fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    except OSError as exc:
        raise _error("pack stage cannot be opened") from exc
    try:
        info = os.fstat(fd)
        yield info.st_dev, info.st_ino
    finally:
        os.close(fd)


def remove_tree(path: Path, *, expect: tuple[int, int] | None = None) -> None:
    """Remove one directory tree without following links, restoring owner access as needed.

    With ``expect`` (device, inode) only that exact directory is removed; anything that replaced
    it since is left alone.
    """

    def clear(fd: int) -> None:
        os.fchmod(fd, 0o700)
        for name in os.listdir(fd):
            if stat.S_ISDIR(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    clear(child)
                finally:
                    os.close(child)
                os.rmdir(name, dir_fd=fd)
            else:
                os.unlink(name, dir_fd=fd)

    try:
        with open_directory(path.parent, error=PackError, label="pack state") as parent:
            try:
                found = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                mode = found.st_mode
            except FileNotFoundError:
                return
            if expect is not None and (found.st_dev, found.st_ino) != expect:
                return
            if not stat.S_ISDIR(mode):
                os.unlink(path.name, dir_fd=parent)
                return
            fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                opened = os.fstat(fd)
                if (opened.st_dev, opened.st_ino) != (found.st_dev, found.st_ino):
                    return  # swapped between stat and open: not the directory that was vetted
                clear(fd)
            finally:
                os.close(fd)
            os.rmdir(path.name, dir_fd=parent)
    except OSError as exc:
        raise _error("pack content could not be removed") from exc
