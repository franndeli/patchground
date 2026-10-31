"""`pgnd list` and `pgnd show`: render local challenge discovery; never build or run anything."""

from __future__ import annotations

import re
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
from patchground.packs import (
    ChallengeDetails,
    DiscoveryError,
    DiscoveryFilters,
    DiscoveryResult,
    discover_challenges,
)
from patchground.packs.models import PackError
from patchground.packs.registry import discover_installed, show_reference
from patchground.spec import ChallengeType, Difficulty

Result = DiscoveryResult | ChallengeDetails
JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON document.")]

# Challenge text is untrusted: drop terminal control sequences before it reaches a terminal.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _clean(value: str) -> str:
    return _CONTROL.sub("", value)


class DiscoveryCommand(TyperCommand):
    """Keep argument-parsing failures inside the one-JSON-document contract under ``--json``."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        json_mode = "--json" in args
        try:
            return super().parse_args(ctx, args)
        except typer.Exit:
            raise
        except Exception as exc:
            if not json_mode:
                raise
            emit_error("environment", "invalid command arguments", True)
            raise typer.Exit(EXIT_ERROR) from exc


def _human_list(console: Console, result: DiscoveryResult) -> None:
    if not result.challenges and not result.invalid:
        console.print(Text(f"no challenges found in {_clean(result.directory)}"))
    for item in result.challenges:
        line = Text()
        line.append(_clean(getattr(item, "reference", item.id)), style="bold")
        line.append(f"  {item.type.value}  {item.difficulty.value}  {item.timebox_minutes}m")
        line.append(f"  {_clean(', '.join(item.languages))}")
        console.print(line)
        console.print(Text(f"    {_clean(item.title)}"))
        console.print(Text(f"    {_clean(item.path)}", style="dim"))
    for bad in result.invalid:
        console.print(Text(f"invalid: {_clean(bad.path)}", style="bold red"))
        for issue in bad.issues:
            console.print(Text(f"    {_clean(issue)}"))


def _human_show(console: Console, result: ChallengeDetails) -> None:
    if not result.valid or result.challenge is None:
        console.print(Text(f"invalid: {_clean(result.path)}", style="bold red"))
        for issue in result.issues:
            console.print(Text(f"    {_clean(issue)}"))
        return
    item = result.challenge
    console.print(Text(f"{_clean(item.title)} ({_clean(item.id)} {_clean(item.version)})"))
    rows = [
        ("type", item.type.value),
        ("difficulty", item.difficulty.value),
        ("timebox", f"{item.timebox_minutes} minutes"),
        ("ai policy", item.ai_policy.value),
        ("languages", ", ".join(item.languages)),
        ("tags", ", ".join(item.tags) or "-"),
        ("hints", str(result.hint_count or 0)),
        ("author", result.author or "-"),
        ("license", result.content_license or "-"),
        ("path", item.path),
    ]
    for label, value in rows:
        console.print(Text(f"{label:<11} {_clean(value)}"))
    console.print(Text(_clean(item.summary)))
    console.print(Text(""))
    console.print(Text(_clean(result.ticket or "")))


def _human(console: Console, result: Result) -> None:
    if isinstance(result, DiscoveryResult):
        _human_list(console, result)
    else:
        _human_show(console, result)


def _invoke(call: Callable[[], Result], json_mode: bool) -> None:
    try:
        result = call()
    except (DiscoveryError, PackError) as exc:
        emit_error("environment", str(exc), json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    except KeyboardInterrupt as exc:
        emit_error("interrupted", "interrupted", json_mode)
        raise typer.Exit(EXIT_INTERRUPTED) from exc
    except Exception as exc:
        # Exception text could quote challenge content; keep it out of the output.
        emit_error("internal", "discovery failed unexpectedly", json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    emit(result.model_dump(mode="json"), lambda console: _human(console, result), json_mode)
    failed = bool(result.invalid) if isinstance(result, DiscoveryResult) else not result.valid
    raise typer.Exit(EXIT_FAILED if failed else EXIT_OK)


def list_challenges(
    directory: Annotated[
        Path | None,
        typer.Argument(help="Folder whose immediate subfolders are challenges (default: here)."),
    ] = None,
    installed: Annotated[
        bool, typer.Option("--installed", help="List installed pack challenges.")
    ] = False,
    type_: Annotated[
        ChallengeType | None, typer.Option("--type", help="Only this challenge type.")
    ] = None,
    lang: Annotated[str | None, typer.Option("--lang", help="Only this language.")] = None,
    difficulty: Annotated[
        Difficulty | None, typer.Option("--difficulty", help="Only this difficulty.")
    ] = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Only challenges with this tag.")] = None,
    json_mode: JsonOption = False,
) -> None:
    """List local challenge folders and report invalid ones; nothing is built or run."""
    filters = DiscoveryFilters(type=type_, lang=lang, difficulty=difficulty, tag=tag)
    if installed and directory is not None:
        emit_error("environment", "--installed cannot be combined with a directory", json_mode)
        raise typer.Exit(EXIT_ERROR)
    _invoke(
        lambda: (
            discover_installed(filters) if installed else discover_challenges(directory, filters)
        ),
        json_mode,
    )


def show(
    path: Annotated[
        str, typer.Argument(help="Local folder, installed ID or pack-name:challenge-id.")
    ],
    json_mode: JsonOption = False,
) -> None:
    """Show a local challenge's metadata and ticket; never the solution or hidden checks."""
    _invoke(lambda: show_reference(path), json_mode)
