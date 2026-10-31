"""Explicit pack-review prompting, shared by start, validate and update."""

from collections.abc import Callable

import typer
from rich.console import Console
from rich.text import Text

from patchground.cli.render import emit, stdout_console
from patchground.packs.models import ConsentRequired, PackReview


def literal(value: str, *, multiline: bool = False) -> str:
    return "".join(
        char if char.isprintable() or (multiline and char in "\n\t") else f"\\u{ord(char):04x}"
        for char in value
    )


def show_review(console: Console, review: PackReview) -> None:
    pack = review.pack
    console.print(Text(f"UNOFFICIAL pack: {pack.name} {pack.version}"))
    console.print(Text(f"commit: {pack.commit}"))
    console.print(Text(f"source: {literal(pack.source)}"))
    console.print(Text(f"approval identity: {pack.identity}"))
    if review.previous_commit:
        console.print(Text(f"previous commit: {review.previous_commit}"))
        for label, names in (
            ("added", review.added),
            ("removed", review.removed),
            ("changed", review.changed),
        ):
            console.print(Text(f"{label}: {', '.join(literal(name) for name in names) or 'none'}"))
    console.print(Text("All indexed build/run recipes follow; control characters are escaped."))
    for recipe in review.recipes:
        console.print(Text(f"Challenge: {recipe.challenge_id}"))
        console.print(Text(f"Dockerfile: {literal(recipe.dockerfile_path)}"))
        for line in literal(recipe.dockerfile, multiline=True).split("\n"):
            console.print(Text("    " + line))
        console.print(Text(f"Services: {', '.join(literal(s) for s in recipe.services) or 'none'}"))
        console.print(Text("Command:"))
        for line in literal(recipe.command, multiline=True).split("\n"):
            console.print(Text("    " + line))
    console.print(
        Text(
            "Builds may use the network. Approval covers this exact whole pack revision, "
            "not future updates. Opening its workspace in your editor can run tooling "
            "outside Docker."
        )
    )


def with_consent[T](operation: Callable[[bool, str | None], T], *, yes: bool, json_mode: bool) -> T:
    try:
        return operation(yes, None)
    except ConsentRequired as required:
        if json_mode:
            raise
        show_review(stdout_console(), required.review)
        try:
            accepted = typer.confirm("Approve this exact pack revision?", default=False)
        except (EOFError, typer.Abort) as exc:
            raise KeyboardInterrupt from exc
        if not accepted:
            raise KeyboardInterrupt from None
        return operation(True, required.review.pack.identity)


def emit_required(required: ConsentRequired, json_mode: bool) -> None:
    emit(
        {
            "error": {"kind": "consent_required", "message": str(required)},
            "review": required.review.model_dump(mode="json"),
        },
        lambda console: show_review(console, required.review),
        json_mode,
    )
