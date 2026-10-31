"""Practice commands: bounded diagnostics, authored hints and read-only local browsing."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.text import Text
from typer.core import TyperCommand

from patchground.cli.render import EXIT_ERROR, EXIT_FAILED, EXIT_INTERRUPTED, emit, emit_error
from patchground.cli.sessions import JsonOption, SessionOption
from patchground.sessions import SessionError
from patchground.sessions.history import history_for_session
from patchground.sessions.models import HistoryResult
from patchground.sessions.practice import (
    CommandRunResult,
    HintResult,
    SessionsList,
    list_sessions,
    reveal_hint,
    run_session_command,
)

Result = HintResult | SessionsList | CommandRunResult | HistoryResult


class RunCommand(TyperCommand):
    """Keep flags after -- literal and never echo command arguments in parse errors."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        options = args[: args.index("--")] if "--" in args else args
        try:
            if "--" not in args and "--help" not in options:
                raise ValueError("missing separator")
            return super().parse_args(ctx, args)
        except typer.Exit:
            raise
        except Exception as exc:
            emit_error(
                "environment", "use run [options] -- <command> [arguments]", "--json" in options
            )
            raise typer.Exit(EXIT_ERROR) from exc


def _display_path(path: Path) -> str:
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def _human(console: Console, result: Result) -> None:
    if isinstance(result, HintResult):
        if result.exhausted:
            console.print(Text("No more authored hints."))
        else:
            console.print(Text(f"Hint {result.index}: {result.hint}"))
            console.print(Text(f"{result.remaining} remaining"))
    elif isinstance(result, SessionsList):
        if not result.sessions:
            console.print(Text("No sessions found."))
        for item in result.sessions:
            console.print(
                Text(
                    f"{item.challenge_id}  {item.state}  {item.last_outcome or 'not checked'}  "
                    f"{_display_path(item.session)}"
                )
            )
        for invalid in result.invalid:
            console.print(Text(f"invalid: {_display_path(invalid.session)}"))
    elif isinstance(result, CommandRunResult):
        console.print(Text("Command output tail (up to 64 KiB; container edits are discarded):"))
        console.print(Text(result.output_tail))
        console.print(Text(f"exit: {result.exit_code}; limit: {result.limit or 'none'}"))
    else:
        console.print(Text(f"history: {result.availability}"))
        for snapshot in result.snapshots:
            console.print(
                Text(
                    f"{snapshot.ts.isoformat()}  {snapshot.kind}  {snapshot.commit[:12]}  "
                    f"{snapshot.check_outcome or ''}"
                )
            )


def _invoke(call: Callable[[], Result], json_mode: bool) -> None:
    try:
        result = call()
    except SessionError as exc:
        emit_error("environment", str(exc), json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    except KeyboardInterrupt as exc:
        emit_error("interrupted", "practice operation interrupted", json_mode)
        raise typer.Exit(EXIT_INTERRUPTED) from exc
    except Exception as exc:
        emit_error("internal", "practice operation failed unexpectedly", json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    emit(result.model_dump(mode="json"), lambda console: _human(console, result), json_mode)
    failed = (isinstance(result, SessionsList) and bool(result.invalid)) or (
        isinstance(result, CommandRunResult) and (result.exit_code != 0 or result.limit is not None)
    )
    if failed:
        raise typer.Exit(EXIT_FAILED)


def hint(session: SessionOption = None, json_mode: JsonOption = False) -> None:
    """Reveal the next authored hint without running code."""
    _invoke(lambda: reveal_hint(session), json_mode)


def sessions(json_mode: JsonOption = False) -> None:
    """List local attempts without selecting one or running Docker."""
    _invoke(list_sessions, json_mode)


def history(session: SessionOption = None, json_mode: JsonOption = False) -> None:
    """Read privacy-filtered private checkpoint history; never restore files."""
    _invoke(lambda: history_for_session(session), json_mode)


def run(
    argv: Annotated[list[str], typer.Argument(help="Container command arguments after --.")],
    session: SessionOption = None,
    json_mode: JsonOption = False,
) -> None:
    """Run a diagnostic command in a disposable container, without hidden checks."""
    _invoke(lambda: run_session_command(argv, session), json_mode)
