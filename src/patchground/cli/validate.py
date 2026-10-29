"""`pgnd validate`: run challenge verification and render the per-step report."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.text import Text

from patchground.cli.render import (
    EXIT_ERROR,
    EXIT_FAILED,
    EXIT_INTERRUPTED,
    EXIT_OK,
    emit,
    emit_error,
    progress,
)
from patchground.verify import (
    StepStatus,
    ValidationReport,
    VerifyEnvironmentError,
    validate_challenge,
)

_MARKS = {
    StepStatus.PASSED: ("✓", "green"),
    StepStatus.FAILED: ("✗", "red"),
    StepStatus.NOT_RUN: ("-", "dim"),
}


def validate(
    path: Annotated[
        Path, typer.Argument(help="Challenge folder (the one holding challenge.yaml).")
    ],
    json_mode: Annotated[
        bool, typer.Option("--json", help="Print one JSON document on stdout.")
    ] = False,
    no_write: Annotated[
        bool, typer.Option("--no-write", help="Do not write verification.json on success.")
    ] = False,
) -> None:
    """Verify a challenge: manifest, image build, broken state fails, reference passes."""
    try:
        with progress(json_mode) as notify:
            report = validate_challenge(path, write=not no_write, progress=notify)
    except VerifyEnvironmentError as exc:
        emit_error("environment", str(exc), json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    except KeyboardInterrupt as exc:
        emit_error("interrupted", "interrupted", json_mode)
        raise typer.Exit(EXIT_INTERRUPTED) from exc
    except Exception as exc:  # last resort: never a traceback, never confused with "invalid"
        emit_error("internal", f"{type(exc).__name__}: {exc}", json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    emit(report.to_dict(), lambda console: _human(console, report), json_mode)
    raise typer.Exit(EXIT_OK if report.valid else EXIT_FAILED)


def _human(console: Console, report: ValidationReport) -> None:
    width = max(len(step.name.value) for step in report.steps)
    for step in report.steps:
        mark, style = _MARKS[step.status]
        line = Text()
        line.append(f"{mark} ", style=style)
        line.append(step.name.value.ljust(width), style="bold")
        line.append(f"  {step.detail}")
        console.print(line)
        for issue_line in step.issue_lines:
            console.print(Text(f"    {issue_line}"))
        for note in step.notes:
            console.print(Text(f"    {note}", style="dim"))
        if step.log_tail:
            for log_line in step.log_tail.splitlines():
                console.print(Text(f"    | {log_line}", style="dim"))
    if report.verification_file is not None:
        console.print(Text(f"wrote {report.verification_file}", style="dim"))
    if report.removed_verification_file is not None:
        console.print(Text(f"removed stale {report.removed_verification_file}", style="dim"))
    failed = report.failed_step
    if report.valid:
        console.print(Text("valid", style="bold green"))
    elif failed is not None:
        console.print(Text(f"invalid: failed at step {failed.value}", style="bold red"))
    else:  # pragma: no cover - every report has a passed or failed step
        console.print(Text("invalid", style="bold red"))
