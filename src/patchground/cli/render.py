"""Shared output: every command renders one result either as Rich text or as one JSON document."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from rich.console import Console
from rich.text import Text

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_ERROR = 2
EXIT_INTERRUPTED = 130


def stdout_console() -> Console:
    return Console(soft_wrap=True, highlight=False)


def stderr_console() -> Console:
    return Console(stderr=True, soft_wrap=True, highlight=False)


def emit(
    result_for_json: dict[str, Any], human: Callable[[Console], None], json_mode: bool
) -> None:
    """Write ``result_for_json`` as the single JSON document on stdout, or call ``human``."""
    if json_mode:
        sys.stdout.write(json.dumps(result_for_json, indent=2, ensure_ascii=True) + "\n")
        sys.stdout.flush()
    else:
        human(stdout_console())


def emit_error(kind: str, message: str, json_mode: bool) -> None:
    """Report an error that stopped the command (JSON on stdout, or text on stderr)."""
    if json_mode:
        emit({"error": {"kind": kind, "message": message}}, lambda _console: None, True)
    else:
        stderr_console().print(Text(f"error: {message}", style="bold red"))


@contextmanager
def progress(json_mode: bool) -> Iterator[Callable[[str], None]]:
    """Yield a callback that shows progress on stderr in human mode (and does nothing in JSON)."""
    if json_mode:
        yield lambda _message: None
        return
    console = stderr_console()
    if not console.is_terminal:
        yield lambda message: console.print(Text(f"{message}…", style="dim"))
        return
    with console.status("starting…") as status:
        yield lambda message: status.update(f"{message}…")
