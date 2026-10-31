"""Private frozen inputs and atomic, independently readable session closure."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, Field, ValidationError

from patchground import sandbox as engine
from patchground.sandbox import SandboxError
from patchground.sessions import store
from patchground.sessions.files import copy_tree, open_directory, open_entry
from patchground.sessions.models import CheckResult, Event, Model, SessionError, SessionRecord, now
from patchground.sessions.workflow import Sandbox, _root, _sanitized
from patchground.spec import ChallengeManifest


@dataclass(frozen=True)
class SubmissionSnapshot:
    session: Path
    original: Path
    final: Path
    hidden: Path
    record: SessionRecord
    manifest: ChallengeManifest
    events: tuple[Event, ...]
    requested_at: datetime
    saved_report: dict[str, object] | None


class SubmissionAudit(Model):
    prefix_size: int = Field(ge=0)
    prefix_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    event: str


class Receipt(Model):
    schema_version: Literal[1]
    requested_at: AwareDatetime
    final_check: CheckResult
    artifacts: dict[str, str]
    audit: SubmissionAudit


def _inventory(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}

    def visit(parent: int, prefix: str) -> None:
        for name in sorted(os.listdir(parent)):
            if not prefix and name == "receipt.json":
                continue
            with open_entry(parent, name) as descriptor:
                info = os.fstat(descriptor)
                key = prefix + name
                if stat.S_ISDIR(info.st_mode):
                    result[key + "/"] = f"directory:{stat.S_IMODE(info.st_mode):o}"
                    visit(descriptor, key + "/")
                else:
                    if info.st_nlink != 1:
                        raise SessionError("submission artifacts must not have hardlinks")
                    digest = hashlib.sha256(stat.S_IMODE(info.st_mode).to_bytes(2, "big"))
                    with os.fdopen(os.dup(descriptor), "rb") as stream:
                        for block in iter(lambda: stream.read(65536), b""):
                            digest.update(block)
                    result[key] = digest.hexdigest()

    with open_directory(path) as parent:
        visit(parent, "")
    return result


def completed(meta: Path) -> tuple[dict[str, object], Receipt] | None:
    """Validate committed artifacts without consulting live workspace files."""
    with open_directory(meta) as parent:
        if "submission" not in os.listdir(parent):  # noqa: PTH208 -- pinned descriptor
            return None
    bundle = meta / "submission"
    try:
        with open_directory(bundle) as parent:
            values: dict[str, str] = {}
            for name in ("receipt.json", "report.json", "report.md"):
                with (
                    store.metadata_file(parent, name) as descriptor,
                    os.fdopen(os.dup(descriptor), "r", encoding="utf-8") as stream,
                ):
                    values[name] = stream.read()
            if set(os.listdir(parent)) != {  # noqa: PTH208 -- pinned descriptor
                "receipt.json",
                "report.json",
                "report.md",
                "final",
            }:
                raise ValueError("unexpected bundle entry")
        with open_directory(bundle / "final"):
            pass
        receipt = Receipt.model_validate_json(values["receipt.json"])
        event = Event.model_validate_json(receipt.audit.event)
        if (
            not receipt.audit.event.endswith("\n")
            or len(receipt.audit.event.splitlines()) != 1
            or event.type != "submitted"
            or event.data != {"requested_at": receipt.requested_at.isoformat()}
        ):
            raise ValueError("inconsistent submission audit receipt")
        if _inventory(bundle) != receipt.artifacts:
            raise ValueError("artifact integrity mismatch")
        report = json.loads(values["report.json"])
        if not isinstance(report, dict):
            raise ValueError("invalid report")
        return report, receipt
    except (OSError, UnicodeError, ValueError, ValidationError) as exc:
        raise SessionError("corrupt or unsafe submission bundle") from exc


def require_active(meta: Path) -> None:
    if completed(meta) is not None:
        raise SessionError("session already submitted: start a new session to practice again")


def audit_contents(raw: bytes, receipt: Receipt) -> tuple[bytes, bytes]:
    """Return parseable audit bytes and a proven missing append suffix; never discard bytes."""
    audit = receipt.audit
    prefix = raw[: audit.prefix_size]
    if (
        len(prefix) != audit.prefix_size
        or hashlib.sha256(prefix).hexdigest() != audit.prefix_sha256
    ):
        raise SessionError("corrupt submission audit: history does not match receipt")
    expected = audit.event.encode("utf-8")
    suffix = raw[audit.prefix_size :]
    if len(suffix) < len(expected) and expected.startswith(suffix):
        return prefix, expected[len(suffix) :]
    if not suffix.startswith(expected):
        raise SessionError("corrupt submission audit: unexpected submission append")
    if not raw.endswith(b"\n"):
        raise SessionError("corrupt submission audit: incomplete unrelated event")
    return raw, b""


def _journal(meta: Path) -> bytes:
    with (
        open_directory(meta) as parent,
        store.metadata_file(parent, "events.jsonl") as descriptor,
        os.fdopen(os.dup(descriptor), "rb") as stream,
    ):
        return stream.read()


def _reconcile(meta: Path, receipt: Receipt) -> None:
    try:
        raw = _journal(meta)
        _, missing = audit_contents(raw, receipt)
        if missing:
            store.append_bytes(meta, missing)
    except (OSError, UnicodeError, SessionError) as exc:
        raise SessionError(
            "submission bundle may already be published; retry submit to reconcile its audit"
        ) from exc


@contextmanager
def prepare_submission(
    session: Path | None = None, *, root: Path | None = None
) -> Iterator[SubmissionSnapshot]:
    requested_at = now()
    try:
        path = store.resolve(session, _root(root))
        meta = path / ".session"
        with store.locked(meta):
            record, manifest, events = store.load(path)
            saved = completed(meta)
            if saved is not None:
                report, receipt = saved
                _reconcile(meta, receipt)
                yield SubmissionSnapshot(
                    path,
                    meta / "original",
                    meta / "submission/final",
                    meta / "hidden",
                    record,
                    manifest,
                    tuple(events),
                    receipt.requested_at,
                    report,
                )
                return
            with tempfile.TemporaryDirectory(
                prefix="patchground-submit-", dir=Path(tempfile.gettempdir()).resolve(strict=True)
            ) as temporary:
                captured = Path(temporary)
                for name, source in (
                    ("original", meta / "original"),
                    ("final", path / "workspace"),
                    ("hidden", meta / "hidden"),
                ):
                    (captured / name).mkdir(mode=0o700)
                    copy_tree(source, captured / name)
                yield SubmissionSnapshot(
                    path,
                    captured / "original",
                    captured / "final",
                    captured / "hidden",
                    record,
                    manifest,
                    tuple(events),
                    requested_at,
                    None,
                )
    except (OSError, UnicodeError, SandboxError) as exc:
        raise SessionError("submission unavailable: storage or frozen image unavailable") from exc


def check_submission(snapshot: SubmissionSnapshot, *, sandbox: Sandbox = engine) -> CheckResult:
    if snapshot.saved_report is not None:
        raise SessionError("session already submitted")
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(
            prefix="patchground-submit-check-", dir=Path(tempfile.gettempdir()).resolve(strict=True)
        ) as temporary:
            clean = Path(temporary)
            copy_tree(snapshot.final, clean)
            copy_tree(snapshot.hidden, clean)
            raw = sandbox.run_check(
                snapshot.record.image_id, [clean], snapshot.manifest.environment.test_command
            )
        return _sanitized(raw, time.monotonic() - started)
    except (OSError, SandboxError) as exc:
        raise SessionError(
            "submission check unavailable: storage or frozen image unavailable"
        ) from exc


def _write(path: Path, text: str) -> None:
    with open_directory(path.parent) as parent:
        descriptor = os.open(
            path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())


def _sync_tree(path: Path) -> None:
    with open_directory(path) as parent:
        for name in os.listdir(parent):  # noqa: PTH208 -- pinned descriptor
            with open_entry(parent, name) as descriptor:
                if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    _sync_tree(path / name)
                else:
                    os.fsync(descriptor)
        os.fsync(parent)


def commit_submission(
    snapshot: SubmissionSnapshot, report: dict[str, object], markdown: str, final_check: CheckResult
) -> None:
    meta = snapshot.session / ".session"
    existing = completed(meta)
    if existing is not None:
        store.load(snapshot.session)
        _reconcile(meta, existing[1])
        return
    published = False
    try:
        # Failed/incomplete staging is deliberately left private and is never treated as closure.
        # Never clean it via a pathname that an editor may have replaced.
        name = ".submission-" + uuid4().hex
        with open_directory(meta) as parent:
            os.mkdir(name, mode=0o700, dir_fd=parent)
            stage = meta / name
            with open_directory(stage) as staged:
                os.mkdir("final", mode=0o700, dir_fd=staged)
            copy_tree(snapshot.final, stage / "final")
            _write(
                stage / "report.json",
                json.dumps(report, ensure_ascii=False, allow_nan=False) + "\n",
            )
            _write(stage / "report.md", markdown)
            store.load(snapshot.session)
            prefix = _journal(meta)
            if not prefix.endswith(b"\n"):
                raise SessionError("corrupt session audit before submission")
            audit_event = (
                Event(
                    ts=now(),
                    type="submitted",
                    data={"requested_at": snapshot.requested_at.isoformat()},
                ).model_dump_json()
                + "\n"
            )
            receipt = Receipt(
                schema_version=1,
                requested_at=snapshot.requested_at,
                final_check=final_check,
                artifacts=_inventory(stage),
                audit=SubmissionAudit(
                    prefix_size=len(prefix),
                    prefix_sha256=hashlib.sha256(prefix).hexdigest(),
                    event=audit_event,
                ),
            )
            _write(
                stage / "receipt.json",
                receipt.model_dump_json(exclude={"final_check": {"passed", "counts"}}) + "\n",
            )
            _sync_tree(stage)
            os.rename(name, "submission", src_dir_fd=parent, dst_dir_fd=parent)
            published = True
            # Closure has committed: any subsequent failure must never reopen the session.
            os.fsync(parent)
        store.load(snapshot.session)
        _reconcile(meta, receipt)
    except (OSError, UnicodeError, SessionError) as exc:
        if published:
            raise SessionError(
                "submission bundle may already be published; retry submit to finish finalization"
            ) from exc
        raise


def read_submission(session: Path | None = None, *, root: Path | None = None) -> dict[str, object]:
    try:
        path = store.resolve(session, _root(root))
        store.load(path)
        saved = completed(path / ".session")
        if saved is None:
            raise SessionError("session not submitted: no final report exists")
        return saved[0]
    except (OSError, UnicodeError) as exc:
        raise SessionError("submission unavailable: invalid session storage") from exc
