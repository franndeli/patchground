"""Bounded pytest test-module mutations in disposable editable layers only."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Literal

from patchground.verify.pytest_adapter import (
    UnsupportedPytest,
    is_test_filename,
    iter_test_definitions,
    parse_module,
    supports_pytest,
)

__all__ = ["Mutation", "UnsupportedTampering", "mutate", "supports_pytest", "test_modules"]

Mutation = Literal["empty", "deleted", "skipped"]


class UnsupportedTampering(Exception):
    """No supported mutation can be established; never report this as verified."""


def _syntax(path: Path) -> ast.Module:
    try:
        return parse_module(path)
    except UnsupportedPytest as exc:
        raise UnsupportedTampering("editable modules are not supported Python source") from exc


def test_modules(layers: list[Path]) -> list[Path]:
    """Select conventional modules with static tests, preserving helper-only modules."""
    candidates = sorted(
        path for layer in layers for path in layer.rglob("*.py") if is_test_filename(path.name)
    )
    return [
        path for path in candidates if next(iter_test_definitions(_syntax(path)), None) is not None
    ]


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
