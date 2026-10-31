"""Thin local-session commands; only structured results, never sandbox output."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.text import Text
from typer.core import TyperCommand

from patchground.cli.render import (
    EXIT_ERROR,
    EXIT_FAILED,
    EXIT_INTERRUPTED,
    EXIT_OK,
    emit,
    emit_error,
)
from patchground.sessions import (
    CheckResult,
    ResetResult,
    SessionError,
    SessionStatus,
    StartedSession,
    check_session,
    reset_session,
    session_status,
    start_session,
)

Result = StartedSession | CheckResult | SessionStatus | ResetResult
JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON document.")]
SessionOption = Annotated[Path | None, typer.Option("--session", help="Select a session path.")]


class SessionCommand(TyperCommand):
    """Keep argument-parsing failures inside the session JSON output contract."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        json_mode = "--json" in args
        try:
            return super().parse_args(ctx, args)
        except typer.Exit:
            raise
        except Exception as exc:
            if not json_mode:
                raise
            emit_error("environment", "invalid session command arguments", True)
            raise typer.Exit(EXIT_ERROR) from exc


def _human(console: Console, result: Result) -> None:
    if isinstance(result, StartedSession):
        console.print(Text(f"started {result.challenge_id}"))
        console.print(Text(str(result.workspace)))
        console.print(Text(result.ticket))
    elif isinstance(result, ResetResult):
        console.print(Text(f"reset {result.challenge_id}; timer and history preserved"))
    elif isinstance(result, SessionStatus):
        console.print(Text(f"session {result.challenge_id}"))
        if result.timer:
            console.print(
                Text(f"elapsed {int(result.elapsed_seconds)}s / {result.timebox_minutes} minutes")
            )
        else:
            console.print(Text("timer off"))
        console.print(Text(f"last check: {result.last_outcome or 'not run'}"))
        if result.last_check is not None:
            _human(console, result.last_check)
    else:
        console.print(Text(f"check: {result.outcome.value}"))
        for test in result.tests:
            console.print(Text(f"{test.status.value}  {test.id}"))
        console.print(Text("  ".join(f"{key}: {value}" for key, value in result.counts.items())))
        if result.limit is not None:
            console.print(Text(f"limit exceeded: {result.limit}"))


def _invoke(call: Callable[[], Result], json_mode: bool) -> None:
    try:
        result = call()
    except SessionError as exc:
        emit_error("environment", str(exc), json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    except KeyboardInterrupt as exc:
        emit_error("interrupted", "interrupted", json_mode)
        raise typer.Exit(EXIT_INTERRUPTED) from exc
    except Exception as exc:
        # Exception text can itself contain untrusted logs or hidden source.
        emit_error("internal", "session operation failed unexpectedly", json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    emit(result.model_dump(mode="json"), lambda console: _human(console, result), json_mode)
    raise typer.Exit(
        EXIT_FAILED if isinstance(result, CheckResult) and not result.passed else EXIT_OK
    )


def start(
    path: Annotated[Path, typer.Argument(help="Local authored challenge folder.")],
    no_timer: Annotated[bool, typer.Option("--no-timer")] = False,
    json_mode: JsonOption = False,
) -> None:
    """Start a new local challenge session."""
    _invoke(lambda: start_session(path, timer=not no_timer), json_mode)


def check(session: SessionOption = None, json_mode: JsonOption = False) -> None:
    """Run checks on a temporary copy of the selected workspace."""
    _invoke(lambda: check_session(session), json_mode)


def reset(
    session: SessionOption = None,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm destructive reset.")] = False,
    json_mode: JsonOption = False,
) -> None:
    """Restore starting files, preserving Git and credential-pattern entries."""
    if not yes:
        if json_mode:
            emit_error("environment", "reset requires --yes in JSON mode", True)
            raise typer.Exit(EXIT_ERROR)
        try:
            confirmed = typer.confirm(
                "Discard workspace edits and ordinary added files? "
                "Git, credential-pattern files, timer and history are preserved. "
                "Filesystem errors may leave a partial reset",
                default=False,
            )
        except (KeyboardInterrupt, EOFError, typer.Abort) as exc:
            emit_error("interrupted", "reset cancelled", False)
            raise typer.Exit(EXIT_INTERRUPTED) from exc
        if not confirmed:
            emit_error("interrupted", "reset cancelled", False)
            raise typer.Exit(EXIT_INTERRUPTED)
    _invoke(lambda: reset_session(session), json_mode)


def status(session: SessionOption = None, json_mode: JsonOption = False) -> None:
    """Show the selected session without requiring Docker."""
    _invoke(lambda: session_status(session), json_mode)
