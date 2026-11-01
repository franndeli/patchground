"""Submit and read immutable local outcomes, never AI judgments."""

from collections.abc import Callable

import typer
from rich.console import Console
from rich.text import Text

from patchground.cli.render import EXIT_ERROR, EXIT_FAILED, EXIT_INTERRUPTED, emit, emit_error
from patchground.cli.sessions import JsonOption, SessionOption
from patchground.report.models import VerifiedReport
from patchground.report.render import render_markdown
from patchground.report.workflow import saved_report, submit_session
from patchground.sessions import SessionError


def _invoke(call: Callable[[], VerifiedReport], json_mode: bool, *, submitting: bool) -> None:
    try:
        result = call()
    except SessionError as exc:
        emit_error("environment", str(exc), json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    except KeyboardInterrupt as exc:
        message = (
            "submission interrupted; retry submit to inspect its state"
            if submitting
            else "report read interrupted"
        )
        emit_error("interrupted", message, json_mode)
        raise typer.Exit(EXIT_INTERRUPTED) from exc
    except Exception as exc:
        emit_error("internal", "report operation failed unexpectedly", json_mode)
        raise typer.Exit(EXIT_ERROR) from exc

    def human(console: Console) -> None:
        console.print(Text(render_markdown(result, terminal=True)))
        if submitting:
            console.print(Text("Attempt complete. Read this report again with: pgnd report"))
            console.print(Text("Try another challenge: pgnd list --builtin"))

    emit(result.model_dump(mode="json"), human, json_mode)
    if submitting and not result.checks.passed:
        raise typer.Exit(EXIT_FAILED)


def submit(session: SessionOption = None, json_mode: JsonOption = False) -> None:
    """Finalize this attempt with fresh checks and an immutable verified-outcomes report."""
    _invoke(lambda: submit_session(session), json_mode, submitting=True)


def report(session: SessionOption = None, json_mode: JsonOption = False) -> None:
    """Read the saved final report without Docker or rerunning checks."""
    _invoke(lambda: saved_report(session), json_mode, submitting=False)
