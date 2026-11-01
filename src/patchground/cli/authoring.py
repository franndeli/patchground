"""Thin authoring command; no build or run side effects."""

from typing import Annotated

import typer
from rich.console import Console
from rich.text import Text

from patchground.authoring import AuthoringError, CreatedChallenge, create_challenge
from patchground.cli.render import EXIT_ERROR, EXIT_INTERRUPTED, emit, emit_error


def _human(console: Console, result: CreatedChallenge) -> None:
    console.print(Text(f"created {result.path} ({result.type}, {result.language})"))
    console.print(Text("Edit the starter, then run:"))
    console.print(Text(f"  pgnd validate {result.path}"))


def new(
    challenge_id: Annotated[str, typer.Argument(help="New challenge id and folder name.")],
    type_: Annotated[
        str, typer.Option("--type", help="Template type (debug or feature).")
    ] = "debug",
    language: Annotated[
        str, typer.Option("--lang", help="Template language (python or typescript).")
    ] = "python",
    json_mode: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
) -> None:
    """Create a runnable authored challenge without building or running it."""
    try:
        result = create_challenge(challenge_id, type_=type_, language=language)
    except AuthoringError as exc:
        emit_error("environment", str(exc), json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    except KeyboardInterrupt as exc:
        emit_error("interrupted", "interrupted", json_mode)
        raise typer.Exit(EXIT_INTERRUPTED) from exc
    except Exception as exc:
        emit_error("internal", "scaffold creation failed unexpectedly", json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    emit(result.model_dump(mode="json"), lambda console: _human(console, result), json_mode)
