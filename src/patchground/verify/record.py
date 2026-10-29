"""Write and read ``verification.json`` in a challenge root."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from patchground import __version__
from patchground.spec.loader import CHALLENGE_MANIFEST
from patchground.verify.result import ValidationReport

VERIFICATION_FILE = "verification.json"
FORMAT = "patchground-verification"
FORMAT_VERSION = 1


def verification_document(report: ValidationReport) -> dict[str, Any]:
    """The ``verification.json`` content for a report whose challenge loaded."""
    if report.challenge is None:
        raise ValueError("a verification document needs a loaded challenge")
    manifest = report.challenge.manifest
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "patchground_version": __version__,
        "challenge": {
            "id": manifest.id,
            "version": manifest.version,
            "spec_version": manifest.spec_version,
        },
        "image_id": report.image_id,
        "validated_at": report.validated_at,
        "steps": [step.to_record() for step in report.steps],
    }


def write_verification(root: Path, document: dict[str, Any]) -> Path:
    """Atomically write ``document`` to ``root/verification.json`` and return its path."""
    target = root / VERIFICATION_FILE
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=root, prefix=f".{VERIFICATION_FILE}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.chmod(0o644)
        tmp.replace(target)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    return target


def remove_verification(folder: Path) -> Path | None:
    """Delete a stale ``verification.json`` from ``folder``; return its path if one was removed.

    A failed validation must not leave an earlier record claiming the challenge is valid. Only a
    Patchground record (see :func:`read_verification`) in a folder holding ``challenge.yaml`` is
    removed; any other file of that name is not ours and is left alone.
    """
    folder = Path(folder)
    target = folder / VERIFICATION_FILE
    if not (target.is_file() or target.is_symlink()):
        return None
    if not (folder / CHALLENGE_MANIFEST).is_file() or read_verification(folder) is None:
        return None
    target.unlink()
    return target


def read_verification(folder: Path) -> dict[str, Any] | None:
    """Return the parsed ``verification.json`` of a challenge folder.

    ``None`` when the file is missing, is not valid JSON, or is not a
    ``patchground-verification`` document of a supported format version — in every such case
    the challenge has no usable verification record and needs validating.
    """
    path = Path(folder) / VERIFICATION_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("format") != FORMAT or data.get("format_version") != FORMAT_VERSION:
        return None
    return data
