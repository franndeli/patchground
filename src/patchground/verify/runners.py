"""Recognize the bounded runner recipes without executing authored commands."""

from __future__ import annotations

import re
import shlex
from pathlib import PurePath, PurePosixPath
from typing import Literal

from patchground.runner_assets import VITEST_COMMAND
from patchground.verify.pytest_adapter import supports_pytest

Runner = Literal["pytest", "vitest"]
VITEST_EXCLUDED_PARTS = frozenset({"node_modules", ".git"})
_SAFE_MODULE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*")


def is_vitest_path(path: PurePath) -> bool:
    return path.name.endswith(".test.ts") and not VITEST_EXCLUDED_PARTS.intersection(path.parts)


def vitest_identity(module: str, name: str) -> str:
    path = PurePosixPath(module)
    identity = f"{module}::{name}"
    if (
        not _SAFE_MODULE.fullmatch(module)
        or not is_vitest_path(path)
        or path.is_absolute()
        or ".." in path.parts
        or any(part.startswith("-") for part in path.parts)
        or not name
        or not identity.isprintable()
        or len(identity) > 240
    ):
        raise ValueError("TypeScript test identity cannot be represented safely")
    return identity


def runner_for(command: str) -> Runner | None:
    if supports_pytest(command):
        return "pytest"
    try:
        if shlex.split(command) == shlex.split(VITEST_COMMAND):
            return "vitest"
    except ValueError:
        pass
    return None
