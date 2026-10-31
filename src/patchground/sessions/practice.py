"""Authored hints, local session browsing and metadata-only command orchestration."""

from __future__ import annotations

import os
import stat
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Protocol

from pydantic import AwareDatetime, Field

from patchground import sandbox as engine
from patchground.sandbox import CommandResult, SandboxError
from patchground.sessions import store
from patchground.sessions.files import copy_tree, no_links, open_directory, safe_path
from patchground.sessions.models import Model, SessionError
from patchground.sessions.submission import require_active
from patchground.sessions.workflow import _root, session_status


class HintResult(Model):
    session: Path
    challenge_id: str
    index: int | None
    hint: str | None
    remaining: int
    exhausted: bool


class SessionListingItem(Model):
    session: Path
    challenge_id: str
    challenge_version: str
    started_at: AwareDatetime
    state: Literal["active", "submitted"]
    last_outcome: str | None
    timer: bool
    elapsed_seconds: float
    timebox_minutes: int


class InvalidSession(Model):
    session: Path
    reason: str


class SessionsList(Model):
    sessions: tuple[SessionListingItem, ...]
    invalid: tuple[InvalidSession, ...]


class CommandRunResult(Model):
    exit_code: int | None
    limit: str | None
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    output_tail: str
    output_tail_only: Literal[True] = True


class CommandSandbox(Protocol):
    def run_command(
        self, image_id: str, layers: Sequence[Path], argv: Sequence[str]
    ) -> CommandResult: ...


def reveal_hint(session: Path | None = None, *, root: Path | None = None) -> HintResult:
    try:
        path = store.resolve(session, _root(root))
        meta = path / ".session"
        with store.locked(meta):
            record, manifest, events = store.load(path)
            require_active(meta)
            indices = [event.data.get("index") for event in events if event.type == "hint_revealed"]
            if (
                any(type(index) is not int for index in indices)
                or indices != list(range(1, len(indices) + 1))
                or len(indices) > len(manifest.hints)
            ):
                raise SessionError("corrupt hint history")
            index = len(indices)
            exhausted = index == len(manifest.hints)
            if not exhausted:
                store.append_event(meta, "hint_revealed", {"index": index + 1})
            return HintResult(
                session=path,
                challenge_id=record.challenge_id,
                index=None if exhausted else index + 1,
                hint=None if exhausted else manifest.hints[index],
                remaining=max(0, len(manifest.hints) - index - 1),
                exhausted=exhausted,
            )
    except (OSError, UnicodeError) as exc:
        raise SessionError("hint unavailable: invalid session storage") from exc


def list_sessions(*, root: Path | None = None) -> SessionsList:
    base = _root(root)
    items: list[SessionListingItem] = []
    invalid: list[InvalidSession] = []
    try:
        no_links(base)
        if not base.exists():
            return SessionsList(sessions=(), invalid=())
        safe_path(base, directory=True)
        with open_directory(base) as parent, os.scandir(parent) as entries:
            names = sorted(entry.name for entry in entries)
        for name in names:
            path = base / name
            try:
                mode = path.lstat().st_mode
                if stat.S_ISLNK(mode):
                    raise SessionError("unsafe session entry")
                if not stat.S_ISDIR(mode):
                    continue
                with open_directory(path) as parent, os.scandir(parent) as entries:
                    if not any(entry.name == ".session" for entry in entries):
                        continue
                record, _, _ = store.load(path)
                status = session_status(path, root=base)
                items.append(
                    SessionListingItem(
                        session=path,
                        challenge_id=record.challenge_id,
                        challenge_version=record.challenge_version,
                        started_at=record.started_at,
                        state=status.state,
                        last_outcome=status.last_outcome,
                        timer=status.timer,
                        elapsed_seconds=status.elapsed_seconds,
                        timebox_minutes=status.timebox_minutes,
                    )
                )
            except (SessionError, OSError, UnicodeError):
                invalid.append(InvalidSession(session=path, reason="unsafe or invalid session"))
    except (OSError, UnicodeError) as exc:
        raise SessionError("sessions unavailable: session directory cannot be read") from exc
    items.sort(key=lambda item: (item.started_at, item.session.name), reverse=True)
    return SessionsList(sessions=tuple(items), invalid=tuple(invalid))


def run_session_command(
    argv: Sequence[str],
    session: Path | None = None,
    *,
    root: Path | None = None,
    sandbox: CommandSandbox = engine,
) -> CommandRunResult:
    if not argv or not argv[0] or any("\0" in argument for argument in argv):
        raise SessionError("run requires a nonempty command after --")
    try:
        path = store.resolve(session, _root(root))
        meta = path / ".session"
        with store.locked(meta):
            record, _, _ = store.load(path)
            require_active(meta)
            started = time.monotonic()
            try:
                with tempfile.TemporaryDirectory(
                    prefix="patchground-command-",
                    dir=Path(tempfile.gettempdir()).resolve(strict=True),
                ) as temporary:
                    captured = Path(temporary)
                    copy_tree(path / "workspace", captured)
                    result = sandbox.run_command(record.image_id, [captured], tuple(argv))
                response = CommandRunResult(
                    exit_code=result.exit_code,
                    limit=result.limit,
                    duration_seconds=time.monotonic() - started,
                    output_tail=result.output_tail,
                )
            except (SandboxError, SessionError, OSError, KeyboardInterrupt) as exc:
                store.append_event(
                    meta,
                    "command_run",
                    {
                        "outcome": "interrupted"
                        if isinstance(exc, KeyboardInterrupt)
                        else "environment_error",
                        "duration_seconds": time.monotonic() - started,
                    },
                )
                raise
            store.append_event(
                meta,
                "command_run",
                {
                    "exit_code": response.exit_code,
                    "limit": response.limit,
                    "duration_seconds": response.duration_seconds,
                },
            )
            return response
    except (OSError, UnicodeError, SandboxError) as exc:
        raise SessionError(
            "command unavailable: session storage or frozen image unavailable"
        ) from exc
