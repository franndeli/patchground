"""Bounded pytest test-module mutations in disposable editable layers only."""

from __future__ import annotations

import ast
import shlex
import tokenize
from pathlib import Path
from typing import Literal

Mutation = Literal["empty", "deleted", "skipped"]


class UnsupportedTampering(Exception):
    """No supported mutation can be established; never report this as verified."""


def supports_pytest(command: str) -> bool:
    """Recognize direct pytest and python -m pytest invocations, not shell pipelines."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return False
    if not words or any(word and all(c in "();<>|&" for c in word) for word in words):
        return False
    if words[0] in ("pytest", "pytest-3"):
        return True
    return (
        len(words) >= 3
        and words[0] in ("python", "python3", "python3.12", "python3.13", "python3.14")
        and words[1:3] == ["-m", "pytest"]
    )


def _syntax(path: Path) -> ast.Module:
    try:
        with tokenize.open(path) as stream:
            return ast.parse(stream.read())
    except (SyntaxError, UnicodeError, LookupError) as exc:
        raise UnsupportedTampering("editable modules are not supported Python source") from exc


def test_modules(layers: list[Path]) -> list[Path]:
    """Select conventional modules with static tests, preserving helper-only modules."""
    candidates = sorted(
        path
        for layer in layers
        for path in layer.rglob("*.py")
        if path.name.startswith("test_") or path.name.endswith("_test.py")
    )
    selected: list[Path] = []
    for path in candidates:
        body = _syntax(path).body
        nodes = list(body)
        for node in body:
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                nodes.extend(node.body)
        if any(
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name.startswith("test_")
            for node in nodes
        ):
            selected.append(path)
    return selected


def mutate(modules: list[Path], mutation: Mutation) -> None:
    for path in modules:
        if mutation == "deleted":
            path.unlink()
        elif mutation == "skipped":
            syntax = _syntax(path)
            names = {node.id for node in ast.walk(syntax) if isinstance(node, ast.Name)}
            alias = "_patchground_anti_gaming_pytest"
            while alias in names:
                alias += "_"
            suffix = (
                f"\nimport pytest as {alias}\n"
                "pytestmark = globals().get('pytestmark', [])\n"
                "pytestmark = (list(pytestmark) if isinstance(pytestmark, (list, tuple)) "
                "else [pytestmark]) + "
                f"[{alias}.mark.skip(reason='Patchground editable-test probe')]\n"
            )
            with path.open("ab") as stream:
                stream.write(suffix.encode("ascii"))
