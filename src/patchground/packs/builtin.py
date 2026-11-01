"""Curated challenges shipped inside the CLI distribution.

They are first-party content, installed together with the code that runs them, so they keep local
behaviour: no pack registry, no consent prompt. A bare ID falls back to them only after local
folders and installed packs.
"""

from __future__ import annotations

import re
from pathlib import Path

import patchground
from patchground.spec.models import SLUG_PATTERN

_CATALOG = "catalog"


def builtin_root() -> Path | None:
    """The bundled catalog of a wheel, or ``examples/`` when running from a source checkout."""
    package = Path(patchground.__file__).resolve().parent
    candidates = [package / _CATALOG]
    if package.parent.name == "src":
        candidates.append(package.parent.parent / "examples")
    for candidate in candidates:
        if candidate.is_dir() and not candidate.is_symlink():
            return candidate
    return None


def builtin_challenge(reference: str) -> Path | None:
    """The bundled folder for a bare challenge ID, if one exists."""
    if not re.fullmatch(SLUG_PATTERN, reference):
        return None
    root = builtin_root()
    if root is None:
        return None
    folder = root / reference
    if folder.is_symlink() or not (folder / "challenge.yaml").is_file():
        return None
    return folder


def is_builtin_path(path: Path) -> bool:
    """Whether ``path`` lies inside the bundled catalog (never written to)."""
    root = builtin_root()
    if root is None:
        return False
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True
