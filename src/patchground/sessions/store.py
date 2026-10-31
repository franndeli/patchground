"""Fixed session layout, typed reads, append-only events and POSIX check locking."""

from __future__ import annotations

import fcntl
import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from patchground.sessions.files import no_links, open_directory, safe_path, tree
from patchground.sessions.models import CheckResult, Event, SessionError, SessionRecord, now
from patchground.spec import ChallengeManifest


def allocate(root: Path, challenge_id: str) -> Path:
    no_links(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    safe_path(root, directory=True)
    stem = f"{date.today().isoformat()}-{challenge_id}"
    suffix = 0
    while True:
        candidate = root / (stem if suffix == 0 else f"{stem}-{suffix}")
        try:
            candidate.mkdir(mode=0o700)
            return candidate
        except FileExistsError:
            suffix += 1


def resolve(session: Path | None, root: Path) -> Path:
    no_links(root)
    if not root.exists():
        raise SessionError("no sessions found: start a challenge, then select it with --session")
    safe_path(root, directory=True)
    selected = (session if session is not None else Path.cwd()).absolute()
    safe_path(selected, directory=True)
    # Normalize '..' only after rejecting links: lexical ancestors alone can
    # incorrectly select a session when the requested path actually escapes it.
    selected = selected.resolve(strict=True)
    for candidate in (selected, *selected.parents):
        if candidate.parent == root.resolve(strict=True):
            return candidate
    raise SessionError("select a session with --session or run inside its workspace")


def load(path: Path) -> tuple[SessionRecord, ChallengeManifest, list[Event]]:
    safe_path(path, directory=True)
    meta = path / ".session"
    safe_path(meta, directory=True)
    safe_path(path / "workspace", directory=True)
    contents: dict[str, str] = {}
    with open_directory(meta) as parent:
        for name in ("session.json", "manifest.json", "TICKET.md", "events.jsonl", "lock"):
            with metadata_file(parent, name) as descriptor:
                if name in ("session.json", "manifest.json", "events.jsonl"):
                    with os.fdopen(os.dup(descriptor), "r", encoding="utf-8") as stream:
                        contents[name] = stream.read()
    tree(meta / "hidden")
    tree(meta / "original")
    try:
        record = SessionRecord.model_validate_json(contents["session.json"])
        manifest = ChallengeManifest.model_validate_json(contents["manifest.json"])
        raw = contents["events.jsonl"]
        if not raw.endswith("\n"):
            raise ValueError("truncated events")
        events = [Event.model_validate_json(line) for line in raw.splitlines()]
        if not events or events[0].type != "session_started":
            raise ValueError("missing start event")
        if events[0].ts != record.started_at or events[0].data != {
            "challenge_id": record.challenge_id
        }:
            raise ValueError("inconsistent start event")
        for event in events:
            if event.type == "check_run":
                check_from_event(event)
        if (record.challenge_id, record.challenge_version) != (manifest.id, manifest.version):
            raise ValueError("inconsistent manifest")
        if manifest.environment.services:
            raise ValueError("unsupported services")
    except (ValidationError, ValueError, UnicodeError) as exc:
        raise SessionError("corrupt session metadata or events") from exc
    return record, manifest, events


def check_from_event(event: Event) -> CheckResult | None:
    if event.data.get("outcome") in ("environment_error", "interrupted"):
        if set(event.data) != {"outcome", "duration_seconds"}:
            raise ValueError("invalid check event")
        duration = event.data["duration_seconds"]
        if not isinstance(duration, int | float) or not 0 <= duration < float("inf"):
            raise ValueError("invalid check duration")
        return None
    data = dict(event.data)
    counts = data.pop("counts", None)
    passed = data.pop("passed", None)
    result = CheckResult.model_validate(data)
    if counts != result.counts or passed != result.passed:
        raise ValueError("inconsistent check result")
    return result


@contextmanager
def metadata_file(parent: int, name: str, flags: int = os.O_RDONLY) -> Iterator[int]:
    """Mutable session metadata must be an unshared regular inode, even after a race."""
    try:
        descriptor = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except OSError as exc:
        raise SessionError("session metadata contains a symlink or is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise SessionError("session metadata must be a regular file without hardlinks")
        yield descriptor
    finally:
        os.close(descriptor)


def append_event(meta: Path, kind: str, data: dict[str, object]) -> None:
    serialized = Event(ts=now(), type=kind, data=data).model_dump_json() + "\n"
    # A check can take minutes: validate the actual append fd after the sandbox returns.
    with (
        open_directory(meta) as parent,
        metadata_file(parent, "events.jsonl", os.O_WRONLY | os.O_APPEND) as descriptor,
        os.fdopen(os.dup(descriptor), "a", encoding="utf-8") as stream,
    ):
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path: Path, value: object) -> None:
    with open_directory(path.parent) as parent:
        descriptor = os.open(
            path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")


@contextmanager
def locked(meta: Path) -> Iterator[None]:
    with (
        open_directory(meta) as parent,
        metadata_file(parent, "lock", os.O_RDWR) as descriptor,
    ):
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SessionError("session busy: another check or reset is running") from exc
        # Release by closing the pinned descriptor, never by reopening/truncating its path.
        yield
