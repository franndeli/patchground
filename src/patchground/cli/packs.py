"""Pinned-pack management; all source/consent/storage decisions belong to packs."""

from collections.abc import Callable
from typing import Annotated

import typer
from rich.console import Console
from rich.text import Text

from patchground.cli.consent import emit_required, literal, with_consent
from patchground.cli.render import EXIT_ERROR, EXIT_FAILED, EXIT_INTERRUPTED, emit, emit_error
from patchground.cli.sessions import JsonOption, SessionCommand
from patchground.packs.models import (
    ConsentRequired,
    PackError,
    PackInfo,
    PackListing,
    PackRemoval,
    PackUpdateResult,
)
from patchground.packs.registry import add_pack, list_packs, remove_pack, update_pack

app = typer.Typer(
    no_args_is_help=True, help="Manage pinned challenge packs without automatic execution."
)
YesOption = Annotated[bool, typer.Option("--yes", help="Explicitly approve this operation.")]
Result = PackInfo | PackListing | PackRemoval | PackUpdateResult


def _info(console: Console, info: PackInfo) -> None:
    pack = info.pack
    console.print(
        Text(
            f"{pack.name} {pack.version} @ {pack.commit}  "
            f"{'active' if info.active else 'cached'}  unofficial  "
            f"{'consented' if info.consented else 'consent required before execution'}"
        )
    )
    console.print(Text(f"source: {literal(pack.source)}"))


def _human(console: Console, result: Result) -> None:
    if isinstance(result, PackInfo):
        _info(console, result)
    elif isinstance(result, PackListing):
        if not result.packs and not result.invalid:
            console.print(Text("No packs installed."))
        for info in result.packs:
            _info(console, info)
        for problem in result.invalid:
            console.print(Text(f"invalid: {literal(problem.name)}: {literal(problem.reason)}"))
    elif isinstance(result, PackRemoval):
        console.print(
            Text(
                f"removed {result.name}: {result.removed_versions} cached versions; "
                "sessions preserved"
            )
        )
    else:
        console.print(Text("updated" if result.changed else "unchanged"))
        _info(console, result.current)


def _invoke(call: Callable[[], Result], json_mode: bool) -> None:
    try:
        result = call()
    except ConsentRequired as exc:
        emit_required(exc, json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    except PackError as exc:
        emit_error("environment", str(exc), json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    except (KeyboardInterrupt, EOFError, typer.Abort) as exc:
        emit_error("interrupted", "pack operation interrupted; inspect current state", json_mode)
        raise typer.Exit(EXIT_INTERRUPTED) from exc
    except Exception as exc:
        emit_error("internal", "pack operation failed unexpectedly", json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    emit(result.model_dump(mode="json"), lambda console: _human(console, result), json_mode)
    if isinstance(result, PackListing) and result.invalid:
        raise typer.Exit(EXIT_FAILED)


@app.command("add", cls=SessionCommand)
def add(
    source: Annotated[str, typer.Argument(help="Public HTTPS URL or local Git repository.")],
    ref: Annotated[str, typer.Option("--ref", help="Branch, tag or commit to pin.")] = "HEAD",
    json_mode: JsonOption = False,
) -> None:
    """Install committed files; never build or run the pack."""
    _invoke(lambda: add_pack(source, ref=ref), json_mode)


@app.command("list", cls=SessionCommand)
def list_installed_packs(json_mode: JsonOption = False) -> None:
    """Show installed revisions and their consent state without execution."""
    _invoke(list_packs, json_mode)


@app.command("update", cls=SessionCommand)
def update(
    name: str,
    ref: Annotated[str | None, typer.Option("--ref", help="Replace the tracked revision.")] = None,
    yes: YesOption = False,
    json_mode: JsonOption = False,
) -> None:
    """Review changes before activating a new immutable revision."""
    _invoke(
        lambda: with_consent(
            lambda approved, identity: update_pack(
                name, ref=ref, yes=approved, expected_identity=identity
            ),
            yes=yes,
            json_mode=json_mode,
        ),
        json_mode,
    )


@app.command("remove", cls=SessionCommand)
def remove(name: str, yes: YesOption = False, json_mode: JsonOption = False) -> None:
    """Remove cached revisions and future-start consent, never existing sessions."""

    def operation() -> PackRemoval:
        if yes:
            return remove_pack(name, yes=True)
        if json_mode:
            raise PackError("pack remove requires --yes in JSON mode")
        info = next(
            (item for item in list_packs().packs if item.pack.name == name and item.active), None
        )
        if info is None:
            raise PackError("pack is not installed")
        if not typer.confirm(
            f"Remove {info.pack.name}, its cached revisions and future-start consent? "
            "Existing sessions are preserved",
            default=False,
        ):
            raise KeyboardInterrupt
        return remove_pack(name, yes=True, expected_identity=info.pack.identity)

    _invoke(operation, json_mode)
