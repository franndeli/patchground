"""Pure pytest recognition shared by anti-gaming probes and regression evidence.

Nothing here executes authored code or touches a container: commands are only tokenised and test
modules are only parsed. Recognition is deliberately narrow (direct ``pytest`` / ``python -m
pytest`` invocations, conventional module names, static ``test_*`` functions and ``Test*``
methods) and anything else is simply not recognised.
"""

from __future__ import annotations

import ast
import shlex
import tokenize
from collections.abc import Iterator
from pathlib import Path

MAX_SOURCE_BYTES = 1024 * 1024
PYTHON_NAMES = ("python", "python3", "python3.12", "python3.13", "python3.14")

TestNode = ast.FunctionDef | ast.AsyncFunctionDef


class UnsupportedPytest(Exception):
    """Source this adapter cannot analyse; messages never carry source text."""


def split_pytest_command(command: str) -> tuple[list[str], list[str]] | None:
    """Return ``(invocation words, arguments)`` for direct pytest, or ``None`` for anything else.

    Shell pipelines, lists, redirections, environment prefixes and wrappers are not recognised.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return None
    if not words or any(word and all(c in "();<>|&" for c in word) for word in words):
        return None
    if words[0] in ("pytest", "pytest-3"):
        return words[:1], words[1:]
    if len(words) >= 3 and words[0] in PYTHON_NAMES and words[1:3] == ["-m", "pytest"]:
        return words[:3], words[3:]
    return None


def supports_pytest(command: str) -> bool:
    """Recognize direct pytest and python -m pytest invocations, not shell pipelines."""
    return split_pytest_command(command) is not None


def parse_module(path: Path) -> ast.Module:
    try:
        with tokenize.open(path) as stream:
            return ast.parse(stream.read())
    except (SyntaxError, UnicodeError, LookupError, ValueError) as exc:
        raise UnsupportedPytest("not supported Python source") from exc


def is_test_filename(name: str) -> bool:
    return name.startswith("test_") or name.endswith("_test.py")


def iter_test_definitions(tree: ast.Module) -> Iterator[tuple[str, TestNode]]:
    """Yield ``(key, node)`` for static tests: ``test_x`` functions and ``TestC::test_x`` methods.

    Duplicate keys are yielded as written; callers decide whether that is ambiguous.
    """
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test_"
        ):
            yield node.name, node
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for member in node.body:
                if isinstance(
                    member, ast.FunctionDef | ast.AsyncFunctionDef
                ) and member.name.startswith("test_"):
                    yield f"{node.name}::{member.name}", member


def test_definitions(path: Path) -> dict[str, TestNode]:
    """Static tests of one module, keyed ``test_x`` or ``TestC::test_x``.

    Raises :class:`UnsupportedPytest` for source over 1 MiB, source that does not parse, and
    duplicate test names (their identity would be ambiguous). Nothing is executed.
    """
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise UnsupportedPytest("Python source is too large to analyse")
    found: dict[str, TestNode] = {}
    for key, node in iter_test_definitions(parse_module(path)):
        if key in found:
            raise UnsupportedPytest("duplicate test names make test identity ambiguous")
        found[key] = node
    return found
