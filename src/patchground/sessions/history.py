"""Filtered immutable checkpoints; learner Git supplies read-only exclusion data."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import uuid
import zlib
from contextlib import suppress
from pathlib import Path
from typing import Literal

from patchground.sessions import store
from patchground.sessions.files import copy_tree, open_directory, open_entry
from patchground.sessions.history_ignore import IgnoreRules, resolve
from patchground.sessions.models import (
    HistoryEntry,
    HistoryResult,
    SessionError,
    SnapshotStatus,
    now,
)

_CONFIG = b"[core]\n\tbare = true\n\trepositoryformatversion = 0\n"
_HEAD = b"ref: refs/heads/unused\n"
_HEX = re.compile(r"[0-9a-f]{40}\Z")
_REF = re.compile(r"refs/patchground/(initial|check)/([0-9a-f]{32})\Z")
_UNAVAILABLE = SnapshotStatus(state="unavailable", detail="Checkpoint capture unavailable")


def _repository(source: Path, destination: Path, entry: HistoryEntry, rules: IgnoreRules) -> None:
    # Configuration discovery already bound this trusted absolute executable before
    # capture. Never search PATH again from the learner or captured-input context.
    executable = rules.executable
    (destination / "objects").mkdir()
    (destination / "refs").mkdir()
    (destination / "HEAD").write_bytes(_HEAD)
    (destination / "config").write_bytes(_CONFIG)
    with tempfile.TemporaryDirectory(prefix="patchground-history-home-") as home:
        env = {
            "PATH": os.defpath,
            "HOME": home,
            "XDG_CONFIG_HOME": home,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "",
            "GIT_PAGER": "cat",
            "LC_ALL": "C",
            "GIT_AUTHOR_NAME": "Patchground",
            "GIT_COMMITTER_NAME": "Patchground",
            "GIT_AUTHOR_EMAIL": "0+patchground@users.noreply.github.com",
            "GIT_COMMITTER_EMAIL": "0+patchground@users.noreply.github.com",
            "GIT_AUTHOR_DATE": entry.ts.isoformat(),
            "GIT_COMMITTER_DATE": entry.ts.isoformat(),
        }
        command = [
            executable,
            "--no-pager",
            "--git-dir=" + str(destination),
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
            "protocol.allow=never",
            "-c",
            "gc.auto=0",
        ]

        def run(*args: str, data: bytes = b"") -> str:
            return (
                subprocess.run(
                    [*command, *args],
                    input=data,
                    cwd=home,
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                .stdout.decode("ascii")
                .strip()
            )

        # Native Git matches captured .gitignore files, copied info/global rules,
        # and no learner metadata/configuration. Only trusted temporary metadata writes.
        (destination / "info").mkdir()
        (destination / "info/exclude").write_bytes(rules.info)
        excludes = Path(home) / "ignore"
        excludes.write_bytes(rules.global_rules)
        command.extend(
            [
                "--work-tree=" + str(source),
                "-c",
                "core.bare=false",
                "-c",
                "core.excludesFile=" + str(excludes),
                "-c",
                "core.ignoreCase=" + str(rules.ignore_case).lower(),
            ]
        )
        paths = [path for path in source.rglob("*") if path.is_file()]
        names = [os.fsencode(path.relative_to(source).as_posix()) for path in paths]
        matched = subprocess.run(
            [*command, "check-ignore", "--no-index", "-z", "--stdin"],
            input=b"\0".join(names) + (b"\0" if names else b""),
            cwd=home,
            env=env,
            capture_output=True,
            timeout=60,
        )
        if matched.returncode not in (0, 1):
            raise SessionError("ignore matching unavailable")
        ignored = set(matched.stdout.split(b"\0"))
        # Exclusion inputs are temporary, never part of published Git metadata.
        (destination / "info/exclude").unlink()
        (destination / "info").rmdir()
        # Plumbing takes raw bytes, never git-add or attributes/clean/smudge filters.
        index = b""
        for path, name in zip(paths, names, strict=True):
            if name in ignored:
                continue
            blob = run("hash-object", "-w", "--stdin", data=path.read_bytes())
            mode = "100755" if path.stat().st_mode & 0o111 else "100644"
            index += (
                f"{mode} {blob}\t".encode("ascii")
                + os.fsencode(path.relative_to(source).as_posix())
                + b"\0"
            )
        env["GIT_INDEX_FILE"] = str(destination / "index")
        run("read-tree", "--empty")
        run("update-index", "-z", "--index-info", data=index)
        tree = run("write-tree")
        message = entry.model_dump(mode="json", exclude={"commit"})
        commit = run("commit-tree", tree, data=json.dumps(message).encode("utf-8"))
        run("update-ref", entry.ref, commit, "0" * 40)
        (destination / "index").unlink()
        # update-ref may create empty log directories; logs are not used or accepted.


def capture(
    meta: Path,
    source: Path,
    *,
    enabled: bool,
    kind: Literal["initial", "check"],
    check_outcome: str | None = None,
    rules: IgnoreRules | None = None,
) -> SnapshotStatus:
    """Best effort only; callers persist returned status with their completed evidence."""
    if not enabled:
        return SnapshotStatus(state="disabled")
    try:
        rules = rules if rules is not None else resolve(source)
        if rules is None:
            return _UNAVAILABLE
        identifier = uuid.uuid4().hex
        ref = f"refs/patchground/{kind}/{identifier}"
        entry = HistoryEntry(ref=ref, commit="", kind=kind, ts=now(), check_outcome=check_outcome)
        with tempfile.TemporaryDirectory(
            prefix="patchground-history-", dir=Path(tempfile.gettempdir()).resolve(strict=True)
        ) as temporary:
            staging = Path(temporary)
            captured = staging / "input"
            captured.mkdir()
            copy_tree(source, captured)
            repository = staging / "repository"
            repository.mkdir()
            _repository(captured, repository, entry, rules)
            with open_directory(meta) as parent:
                with suppress(FileExistsError):
                    os.mkdir("history.git", mode=0o700, dir_fd=parent)
                with open_entry(parent, "history.git", os.O_RDONLY | os.O_DIRECTORY) as history:
                    existing = _inventory(history)
                    _objects(existing)
                    _publish(repository, history)
                    os.fsync(history)
                os.fsync(parent)
        return SnapshotStatus(state="recorded", ref=ref)
    except (Exception, KeyboardInterrupt):
        # This optional boundary must preserve completed check evidence, including
        # unexpected plumbing errors or an interrupt while creating a checkpoint.
        return _UNAVAILABLE


def _publish(source: Path, target: int) -> None:
    """Append only: share validated objects, publish each new ref exactly once."""
    with open_directory(source) as parent:

        def copy(folder: int, destination: int, prefix: str) -> None:
            # Publish refs last, after all objects and fixed repository metadata are durable.
            for name in sorted(os.listdir(folder), key=lambda value: value == "refs"):
                with open_entry(folder, name) as descriptor:
                    path = prefix + name
                    if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                        with suppress(FileExistsError):
                            os.mkdir(name, mode=0o700, dir_fd=destination)
                        with open_entry(destination, name, os.O_RDONLY | os.O_DIRECTORY) as child:
                            copy(descriptor, child, path + "/")
                    else:
                        with os.fdopen(os.dup(descriptor), "rb") as reader:
                            data = reader.read()
                        try:
                            output = os.open(
                                name,
                                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                0o600,
                                dir_fd=destination,
                            )
                        except FileExistsError:
                            if path.startswith("refs/"):
                                raise SessionError("checkpoint ref already exists") from None
                            with (
                                store.metadata_file(destination, name) as existing,
                                os.fdopen(os.dup(existing), "rb") as stream,
                            ):
                                saved = stream.read()
                            if path.startswith("objects/"):
                                equal = zlib.decompress(saved) == zlib.decompress(data)
                            else:
                                equal = saved == data
                            if not equal:
                                raise SessionError(
                                    "refusing to overwrite private Git metadata"
                                ) from None
                        else:
                            with os.fdopen(output, "wb") as writer:
                                writer.write(data)
                                writer.flush()
                                os.fsync(writer.fileno())
            os.fsync(destination)

        copy(parent, target, "")


def _inventory(root: int) -> dict[str, bytes]:
    contents: dict[str, bytes] = {}

    def visit(parent: int, prefix: str) -> None:
        for name in os.listdir(parent):
            with open_entry(parent, name) as descriptor:
                info = os.fstat(descriptor)
                path = prefix + name
                if stat.S_ISDIR(info.st_mode):
                    if path not in (
                        "objects",
                        "refs",
                        "refs/patchground",
                        "refs/patchground/initial",
                        "refs/patchground/check",
                    ) and not re.fullmatch(r"objects/[0-9a-f]{2}", path):
                        raise SessionError("unsafe checkpoint metadata")
                    visit(descriptor, path + "/")
                else:
                    if info.st_nlink != 1 or not (
                        path in ("HEAD", "config")
                        or _REF.fullmatch(path)
                        or re.fullmatch(r"objects/[0-9a-f]{2}/[0-9a-f]{38}", path)
                    ):
                        raise SessionError("unsafe checkpoint metadata")
                    with os.fdopen(os.dup(descriptor), "rb") as stream:
                        contents[path] = stream.read()

    visit(root, "")
    # Missing fixed files can be completed on retry; existing bytes are never replaced.
    if contents.get("HEAD", _HEAD) != _HEAD or contents.get("config", _CONFIG) != _CONFIG:
        raise SessionError("unsafe checkpoint configuration")
    return contents


def _objects(contents: dict[str, bytes]) -> dict[str, bytes]:
    objects: dict[str, bytes] = {}
    for path, data in contents.items():
        if path.startswith("objects/"):
            oid = path.removeprefix("objects/").replace("/", "")
            expanded = zlib.decompress(data)
            if hashlib.sha1(expanded, usedforsecurity=False).hexdigest() != oid:
                raise SessionError("corrupt checkpoint object")
            header, body = expanded.split(b"\0", 1)
            if int(header.split(b" ")[1]) != len(body):
                raise SessionError("corrupt checkpoint object")
            objects[oid] = expanded
    return objects


def _read(meta: Path, ref: str) -> HistoryEntry:
    match = _REF.fullmatch(ref)
    if match is None:
        raise SessionError("invalid checkpoint reference")
    with open_directory(meta / "history.git") as root:
        contents = _inventory(root)
    if contents.get("HEAD") != _HEAD or contents.get("config") != _CONFIG:
        raise SessionError("incomplete checkpoint configuration")
    commit = contents.get(ref, b"").decode("ascii").strip()
    if not _HEX.fullmatch(commit):
        raise SessionError("missing checkpoint commit")
    objects = _objects(contents)

    def validate_tree(oid: str) -> None:
        raw = objects[oid]
        if not raw.startswith(b"tree "):
            raise SessionError("missing checkpoint tree")
        remaining = raw.split(b"\0", 1)[1]
        while remaining:
            header, rest = remaining.split(b"\0", 1)
            mode, name = header.split(b" ", 1)
            if not name or b"/" in name or len(rest) < 20:
                raise SessionError("invalid checkpoint tree")
            child = rest[:20].hex()
            remaining = rest[20:]
            if mode == b"40000":
                validate_tree(child)
            elif mode not in (b"100644", b"100755") or not objects[child].startswith(b"blob "):
                raise SessionError("invalid checkpoint file")

    raw = objects[commit]
    if not raw.startswith(b"commit "):
        raise SessionError("invalid checkpoint commit")
    body = raw.split(b"\0", 1)[1]
    tree = body.split(b"\n", 1)[0].removeprefix(b"tree ").decode("ascii")
    validate_tree(tree)
    entry = HistoryEntry.model_validate({**json.loads(body.split(b"\n\n", 1)[1]), "commit": commit})
    if entry.ref != ref or entry.kind != match[1]:
        raise SessionError("inconsistent checkpoint metadata")
    return entry


def history_for_session(session: Path | None = None, *, root: Path | None = None) -> HistoryResult:
    """Read evidence-backed checkpoints, including after submission, without repair."""
    root = (root if root is not None else Path.home() / "patchground" / "sessions").absolute()
    path = store.resolve(session, root)
    record, _manifest, events = store.load(path)
    if not record.history_enabled:
        return HistoryResult(session=path, enabled=False, availability="disabled", snapshots=())
    snapshots: list[HistoryEntry] = []
    unavailable = False
    seen: set[str] = set()
    for event in events:
        status = None
        try:
            if event.type == "history_recorded":
                status = SnapshotStatus.model_validate(event.data)
            elif event.type == "check_run" and event.data.get("history") is not None:
                status = SnapshotStatus.model_validate(event.data["history"])
        except ValueError:
            unavailable = True
            continue
        if status is None:
            continue
        if status.state != "recorded" or status.ref is None:
            unavailable = True
            continue
        try:
            if status.ref in seen:
                raise SessionError("duplicate checkpoint evidence")
            entry = _read(path / ".session", status.ref)
            expected = "initial" if event.type == "history_recorded" else "check"
            if entry.kind != expected or entry.check_outcome != (
                str(event.data["outcome"]) if expected == "check" else None
            ):
                raise SessionError("checkpoint does not match evidence")
            snapshots.append(entry)
            seen.add(status.ref)
        except Exception:
            # Untrusted private checkpoint bytes never invalidate practice evidence.
            unavailable = True
    return HistoryResult(
        session=path,
        enabled=True,
        availability="unavailable" if unavailable or not snapshots else "available",
        snapshots=tuple(snapshots),
    )
