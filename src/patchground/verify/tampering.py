"""Bounded pytest test-module mutations in disposable editable layers only."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Literal

from patchground.verify.pytest_adapter import (
    UnsupportedPytest,
    is_test_filename,
    iter_test_definitions,
    supports_pytest,
)
from patchground.verify.pytest_adapter import (
    parse_module as parse_pytest_module,
)
from patchground.verify.runners import Runner, is_vitest_path, vitest_identity
from patchground.verify.vitest_adapter import UnsupportedVitest, parse_module, skip_module

__all__ = [
    "Mutation",
    "UnsupportedTampering",
    "mutate",
    "supports_pytest",
    "test_modules",
    "vitest_identities",
]

Mutation = Literal["empty", "deleted", "skipped"]


class UnsupportedTampering(Exception):
    """No supported mutation can be established; never report this as verified."""


def _syntax(path: Path) -> ast.Module:
    try:
        return parse_pytest_module(path)
    except UnsupportedPytest as exc:
        raise UnsupportedTampering("editable modules are not supported Python source") from exc


def _vitest_modules(layers: list[Path]) -> list[tuple[Path, str]]:
    return [
        (path, path.relative_to(layer).as_posix())
        for layer in layers
        for path in sorted(layer.rglob("*.test.ts"))
        if is_vitest_path(path.relative_to(layer))
    ]


def vitest_identities(layers: list[Path]) -> Counter[str]:
    """Expected editable identities, checked against actual collection before mutation."""
    try:
        return Counter(
            vitest_identity(relative, name)
            for path, relative in _vitest_modules(layers)
            for name in parse_module(path).definitions
        )
    except (UnsupportedVitest, ValueError) as exc:
        raise UnsupportedTampering(
            "TypeScript test identities cannot be established safely"
        ) from exc


def test_modules(layers: list[Path], *, runner: Runner = "pytest") -> list[Path]:
    """Select conventional modules with static tests, preserving helper-only modules."""
    if runner == "vitest":
        try:
            return [path for path, _ in _vitest_modules(layers) if parse_module(path).definitions]
        except UnsupportedVitest as exc:
            raise UnsupportedTampering("unsupported TypeScript test module") from exc
    candidates = sorted(
        path for layer in layers for path in layer.rglob("*.py") if is_test_filename(path.name)
    )
    return [
        path for path in candidates if next(iter_test_definitions(_syntax(path)), None) is not None
    ]


def mutate(modules: list[Path], mutation: Mutation, *, runner: Runner = "pytest") -> None:
    for path in modules:
        if mutation == "deleted":
            path.unlink()
        elif mutation == "skipped" and runner == "vitest":
            try:
                skip_module(path)
            except UnsupportedVitest as exc:
                raise UnsupportedTampering("unsupported TypeScript skip mutation") from exc
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
