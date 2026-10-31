"""Bounded file-scope and structural-test facts; never infer semantic test quality."""

from __future__ import annotations

import ast
import hashlib
import os
import stat
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from patchground.sessions.files import open_directory, open_entry, tree
from patchground.verify.pytest_adapter import UnsupportedPytest, supports_pytest, test_definitions

TEXT_LIMIT = 1024 * 1024


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FileChange(Fact):
    path: str
    kind: Literal["added", "deleted", "modified"]
    added_lines: int | None
    removed_lines: int | None
    outside_expected: bool | None


class DiffEvidence(Fact):
    expected_paths: tuple[str, ...]
    files: tuple[FileChange, ...]


class AssertionReduction(Fact):
    test: str
    before: int
    after: int


class StructureEvidence(Fact):
    status: Literal["established", "not_established"]
    reason: str
    removed_files: tuple[str, ...] = ()
    removed_tests: tuple[str, ...] = ()
    assertion_reductions: tuple[AssertionReduction, ...] = ()
    unsupported_files: tuple[str, ...] = ()


def _file_paths(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in tree(root, skip=True):
        with open_directory(path.parent) as parent, open_entry(parent, path.name) as descriptor:
            if stat.S_ISREG(os.fstat(descriptor).st_mode):
                result[path.relative_to(root).as_posix()] = path
    return result


def _content(path: Path | None) -> tuple[str | None, list[str] | None]:
    if path is None:
        return None, []
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    length = 0
    with (
        open_directory(path.parent) as parent,
        open_entry(parent, path.name) as descriptor,
        os.fdopen(os.dup(descriptor), "rb") as stream,
    ):
        mode = os.fstat(descriptor).st_mode
        digest.update(b"executable:" if mode & 0o111 else b"ordinary:")
        while chunk := stream.read(65536):
            digest.update(chunk)
            length += len(chunk)
            if length <= TEXT_LIMIT:
                chunks.append(chunk)
    if length > TEXT_LIMIT:
        return digest.hexdigest(), None
    content = b"".join(chunks)
    if b"\0" in content:
        return digest.hexdigest(), None
    try:
        return digest.hexdigest(), content.decode("utf-8").splitlines(keepends=True)
    except UnicodeError:
        return digest.hexdigest(), None


def diff_evidence(original: Path, final: Path, expected_paths: tuple[str, ...]) -> DiffEvidence:
    before, after = _file_paths(original), _file_paths(final)
    changes: list[FileChange] = []
    for name in sorted(before.keys() | after.keys()):
        old_hash, old_lines = _content(before.get(name))
        new_hash, new_lines = _content(after.get(name))
        if old_hash == new_hash:
            continue
        added: int | None = None
        removed: int | None = None
        if old_lines is not None and new_lines is not None:
            added = removed = 0
            for operation, i, j, a, b in SequenceMatcher(None, old_lines, new_lines).get_opcodes():
                if operation != "equal":
                    removed += j - i
                    added += b - a
        outside = None
        if expected_paths:
            outside = not any(
                name == expected.rstrip("/") or name.startswith(expected.rstrip("/") + "/")
                for expected in expected_paths
            )
        changes.append(
            FileChange(
                path=name,
                kind="added"
                if name not in before
                else "deleted"
                if name not in after
                else "modified",
                added_lines=added,
                removed_lines=removed,
                outside_expected=outside,
            )
        )
    return DiffEvidence(expected_paths=expected_paths, files=tuple(changes))


def structural_evidence(original: Path, final: Path, command: str) -> StructureEvidence:
    if not supports_pytest(command):
        return StructureEvidence(status="not_established", reason="unsupported test runner")
    before, after = _file_paths(original), _file_paths(final)
    removed_files: list[str] = []
    removed_tests: list[str] = []
    reductions: list[AssertionReduction] = []
    unsupported: list[str] = []
    for name in sorted(before.keys() | after.keys()):
        path = Path(name)
        if path.suffix != ".py" or not (
            path.name.startswith("test_") or path.name.endswith("_test.py")
        ):
            continue
        try:
            old = test_definitions(before[name]) if name in before else {}
            new = test_definitions(after[name]) if name in after else {}
        except UnsupportedPytest:
            unsupported.append(name)
            continue
        if old and name not in after:
            removed_files.append(name)
        removed_tests.extend(f"{name}::{test}" for test in sorted(old.keys() - new.keys()))
        for test in sorted(old.keys() & new.keys()):
            previous = sum(isinstance(node, ast.Assert) for node in ast.walk(old[test]))
            current = sum(isinstance(node, ast.Assert) for node in ast.walk(new[test]))
            if current < previous:
                reductions.append(
                    AssertionReduction(test=f"{name}::{test}", before=previous, after=current)
                )
    return StructureEvidence(
        status="not_established" if unsupported else "established",
        reason="some test source is unsupported" if unsupported else "structural counts only",
        removed_files=tuple(removed_files),
        removed_tests=tuple(removed_tests),
        assertion_reductions=tuple(reductions),
        unsupported_files=tuple(unsupported),
    )
