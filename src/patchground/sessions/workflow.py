"""Start, check and status; sandbox is injected at the execution boundary."""

from __future__ import annotations

import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from patchground import sandbox as engine
from patchground.sandbox import BuildResult, RunOutcome, RunResult, SandboxError, TestStatus
from patchground.sessions import git, store
from patchground.sessions.files import copy_tree, readonly, remove_partial, safe_path
from patchground.sessions.models import (
    CheckResult,
    CheckTest,
    Event,
    SessionError,
    SessionRecord,
    SessionStatus,
    StartedSession,
    now,
)
from patchground.spec import ManifestError, load_challenge


class Sandbox(Protocol):
    """Only execution capabilities sessions require; no engine SDK leaks upward."""

    def build_image(self, dockerfile: Path, *, name: str) -> BuildResult: ...

    def run_check(self, image_id: str, layers: Sequence[Path], command: str) -> RunResult: ...


def _root(root: Path | None) -> Path:
    return (root if root is not None else Path.home() / "patchground" / "sessions").absolute()


def start_session(
    path: Path, *, root: Path | None = None, timer: bool = True, sandbox: Sandbox = engine
) -> StartedSession:
    """Start an authored local challenge, freezing all future check inputs."""
    partial: Path | None = None
    try:
        try:
            challenge = load_challenge(path)
        except ManifestError as exc:
            # Keep file/line diagnostics, but do not echo arbitrary manifest values.
            locations = ", ".join(f"{issue.file.name}:{issue.line or 1}" for issue in exc.issues)
            raise SessionError(f"invalid challenge manifest or unsafe paths ({locations})") from exc
        manifest = challenge.manifest
        if manifest.environment.services:
            raise SessionError("services are not supported by local sessions yet")
        partial = store.allocate(_root(root), manifest.id)
        workspace = partial / "workspace"
        meta = partial / ".session"
        for folder in (workspace, meta, meta / "hidden", meta / "original"):
            folder.mkdir(mode=0o700)
        copy_tree(challenge.root / "workspace", workspace)
        if manifest.checks.visible is not None:
            copy_tree(challenge.root / manifest.checks.visible, workspace)
        copy_tree(workspace, meta / "original")
        readonly(meta / "original")
        copy_tree(challenge.root / manifest.checks.hidden, meta / "hidden")
        safe_path(challenge.root / "TICKET.md", directory=False)
        ticket = (challenge.root / "TICKET.md").read_text(encoding="utf-8")
        (meta / "TICKET.md").write_text(ticket, encoding="utf-8")
        (meta / "TICKET.md").chmod(0o600)
        store.write_json(meta / "manifest.json", manifest.model_dump(mode="json"))
        git.initialize(workspace)
        built = sandbox.build_image(
            challenge.root / manifest.environment.dockerfile, name=manifest.id
        )
        record = SessionRecord(
            challenge_id=manifest.id,
            challenge_version=manifest.version,
            source=str(challenge.root),
            image_id=built.image_id,
            started_at=now(),
            timer=timer,
        )
        store.write_json(meta / "session.json", record.model_dump(mode="json"))
        event = Event(
            ts=record.started_at, type="session_started", data={"challenge_id": manifest.id}
        )
        (meta / "events.jsonl").write_text(event.model_dump_json() + "\n", encoding="utf-8")
        (meta / "events.jsonl").chmod(0o600)
        (meta / "lock").touch(mode=0o600)
        return StartedSession(
            session=partial,
            workspace=workspace,
            challenge_id=manifest.id,
            timer=timer,
            ticket=ticket,
        )
    except BaseException as exc:
        if partial is not None:
            remove_partial(partial)
        if isinstance(exc, OSError | UnicodeError | SandboxError):
            raise SessionError(
                "could not start session: filesystem, Git or image build unavailable"
            ) from exc
        raise


def _sanitized(result: RunResult, duration: float) -> CheckResult:
    tests = tuple(
        CheckTest(id="".join(c for c in test.id if c.isprintable())[:240], status=test.status)
        for test in result.tests
    )
    outcome = result.outcome
    if outcome == RunOutcome.PASSED:
        if not tests or any(t.status == TestStatus.ERRORED for t in tests):
            outcome = RunOutcome.ERRORED
        elif any(t.status != TestStatus.PASSED for t in tests):
            outcome = RunOutcome.FAILED
    return CheckResult(
        outcome=outcome,
        tests=tests,
        duration_seconds=duration,
        limit=result.limit if result.limit in ("timeout", "memory") else None,
    )


def check_session(
    session: Path | None = None, *, root: Path | None = None, sandbox: Sandbox = engine
) -> CheckResult:
    """Check a temporary clean copy; never invoke Git or mutate the user's workspace."""
    try:
        path = store.resolve(session, _root(root))
        store.load(path)
        meta = path / ".session"
        with store.locked(meta):
            record, manifest, _events = store.load(path)
            from patchground.sessions.submission import require_active

            require_active(meta)
            started = time.monotonic()
            try:
                # Canonicalize only the system temp parent (e.g. macOS /var),
                # before creating our private directory; never resolve user trees.
                with tempfile.TemporaryDirectory(
                    prefix="patchground-check-",
                    dir=Path(tempfile.gettempdir()).resolve(strict=True),
                ) as temp:
                    clean = Path(temp)
                    copy_tree(path / "workspace", clean)
                    copy_tree(meta / "hidden", clean)
                    raw = sandbox.run_check(
                        record.image_id, [clean], manifest.environment.test_command
                    )
                result = _sanitized(raw, time.monotonic() - started)
            except (SandboxError, OSError, SessionError, KeyboardInterrupt) as exc:
                store.append_event(
                    meta,
                    "check_run",
                    {
                        "outcome": "interrupted"
                        if isinstance(exc, KeyboardInterrupt)
                        else "environment_error",
                        "duration_seconds": time.monotonic() - started,
                    },
                )
                raise
            store.append_event(meta, "check_run", result.model_dump(mode="json"))
            return result
    except (OSError, UnicodeError, SandboxError) as exc:
        raise SessionError(
            "check unavailable: session storage or frozen image unavailable"
        ) from exc


def session_status(session: Path | None = None, *, root: Path | None = None) -> SessionStatus:
    """Read session state without Docker, lock creation or any filesystem writes."""
    try:
        path = store.resolve(session, _root(root))
        record, manifest, events = store.load(path)
        from patchground.sessions.submission import completed

        saved = completed(path / ".session")
        receipt = saved[1] if saved else None
        last = next((event for event in reversed(events) if event.type == "check_run"), None)
        return SessionStatus(
            session=path,
            workspace=path / "workspace",
            challenge_id=record.challenge_id,
            timer=record.timer,
            state="submitted" if receipt else "active",
            submitted_at=receipt.requested_at if receipt else None,
            elapsed_seconds=max(
                0.0,
                ((receipt.requested_at if receipt else now()) - record.started_at).total_seconds(),
            )
            if record.timer
            else 0,
            timebox_minutes=manifest.timebox_minutes,
            last_check=receipt.final_check
            if receipt
            else store.check_from_event(last)
            if last
            else None,
            last_outcome=receipt.final_check.outcome.value
            if receipt
            else str(last.data["outcome"])
            if last
            else None,
        )
    except (OSError, UnicodeError) as exc:
        raise SessionError(
            "status unavailable: invalid session storage or no session selected"
        ) from exc
