"""Load challenge and pack folders into validated objects, reporting every problem with its line.

Parsing uses ruamel.yaml round-trip mode so each value keeps its source position. All problems
(YAML, schema, filesystem) are collected in one pass and raised together as a ``ManifestError``.
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from pydantic_core import ErrorDetails
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import MarkedYAMLError, YAMLError
from ruamel.yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from patchground.spec.models import (
    SLUG_PATTERN,
    ChallengeManifest,
    PackManifest,
    relative_path_problem,
)

CHALLENGE_MANIFEST = "challenge.yaml"
PACK_MANIFEST = "pack.yaml"
TICKET_FILE = "TICKET.md"
WORKSPACE_DIR = "workspace"

MAX_MANIFEST_BYTES = 1024 * 1024
"""Manifests are small; anything larger is rejected before parsing."""

MAX_YAML_DEPTH = 64
"""Maximum nesting depth accepted by the YAML composer."""

Loc = tuple[str | int, ...]


def _normalized(path: Path) -> Path:
    """Absolute, lexically normalized path (symlinks are not followed)."""
    return Path(os.path.normpath(path.absolute()))


# --------------------------------------------------------------------------------------------------
# Public types
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestIssue:
    """One problem found while loading a manifest. ``line`` is 1-based."""

    file: Path
    line: int | None
    field: str | None
    message: str

    def format(self, relative_to: Path | None = None) -> str:
        """Render as ``file:line: field: message``, ``file`` relative to ``relative_to``."""
        shown = str(self.file)
        if relative_to is not None:
            file_abs = _normalized(self.file)
            base_abs = _normalized(relative_to)
            if file_abs.is_relative_to(base_abs):
                shown = file_abs.relative_to(base_abs).as_posix()
        location = shown if self.line is None else f"{shown}:{self.line}"
        if self.field:
            return f"{location}: {self.field}: {self.message}"
        return f"{location}: {self.message}"

    def __str__(self) -> str:
        return self.format()


class ManifestError(Exception):
    """Raised with every problem found in a challenge or pack folder."""

    def __init__(self, issues: Sequence[ManifestIssue]) -> None:
        self.issues: list[ManifestIssue] = list(issues)
        super().__init__("\n".join(str(issue) for issue in self.issues))


@dataclass(frozen=True)
class Challenge:
    """A validated challenge folder."""

    root: Path
    manifest_path: Path
    manifest: ChallengeManifest


@dataclass(frozen=True)
class Pack:
    """A validated pack folder."""

    root: Path
    manifest_path: Path
    manifest: PackManifest


# --------------------------------------------------------------------------------------------------
# YAML parsing with positions
# --------------------------------------------------------------------------------------------------


def _make_yaml(*, allow_duplicate_keys: bool) -> YAML:
    yaml = YAML(typ="rt", pure=True)
    yaml.allow_duplicate_keys = allow_duplicate_keys
    yaml.max_depth = MAX_YAML_DEPTH
    return yaml


def _line(mark: Any) -> int | None:
    line = getattr(mark, "line", None)
    return line + 1 if isinstance(line, int) else None


def _duplicate_key_issues(node: Node, file: Path) -> list[ManifestIssue]:
    """Find every duplicate mapping key in the composed node graph (aliases visited once)."""
    issues: list[ManifestIssue] = []
    seen_nodes: set[int] = set()
    stack: list[Node] = [node]
    while stack:
        current = stack.pop()
        if id(current) in seen_nodes:
            continue
        seen_nodes.add(id(current))
        if isinstance(current, MappingNode):
            first_line: dict[str, int | None] = {}
            for key_node, value_node in current.value:
                stack.append(value_node)
                if not isinstance(key_node, ScalarNode) or key_node.value == "<<":
                    continue
                key = str(key_node.value)
                line = _line(key_node.start_mark)
                if key in first_line:
                    where = first_line[key]
                    suffix = f" (first defined on line {where})" if where is not None else ""
                    issues.append(ManifestIssue(file, line, None, f"duplicate key '{key}'{suffix}"))
                else:
                    first_line[key] = line
        elif isinstance(current, SequenceNode):
            stack.extend(current.value)
    issues.sort(key=lambda issue: issue.line or 0)
    return issues


def _parse_yaml(path: Path, issues: list[ManifestIssue]) -> Any:
    """Parse ``path``; append problems to ``issues``. Returns the round-trip data or ``None``."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        issues.append(ManifestIssue(path, None, None, f"cannot read file: {exc.strerror}"))
        return None
    if size > MAX_MANIFEST_BYTES:
        issues.append(
            ManifestIssue(path, None, None, f"file is larger than {MAX_MANIFEST_BYTES} bytes")
        )
        return None
    try:
        text = path.read_bytes().decode("utf-8")
    except OSError as exc:
        issues.append(ManifestIssue(path, None, None, f"cannot read file: {exc.strerror}"))
        return None
    except UnicodeDecodeError:
        issues.append(ManifestIssue(path, None, None, "file is not valid UTF-8"))
        return None

    try:
        node = _make_yaml(allow_duplicate_keys=False).compose(text)
        if node is not None:
            issues.extend(_duplicate_key_issues(node, path))
        data = _make_yaml(allow_duplicate_keys=True).load(text)
    except MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        problem = exc.problem or exc.context or "invalid YAML"
        context = f" ({exc.context})" if exc.context and exc.problem else ""
        issues.append(ManifestIssue(path, _line(mark), None, f"YAML error: {problem}{context}"))
        return None
    except YAMLError as exc:
        issues.append(ManifestIssue(path, None, None, f"YAML error: {exc}"))
        return None
    except RecursionError:
        issues.append(ManifestIssue(path, None, None, "YAML error: document is nested too deeply"))
        return None

    if not isinstance(data, CommentedMap):
        issues.append(
            ManifestIssue(path, 1, None, f"{path.name} must contain a mapping of keys at the top")
        )
        return None
    return data


def _to_plain(value: Any, memo: dict[int, Any] | None = None) -> Any:
    """Convert ruamel round-trip containers and scalar subclasses into plain Python values.

    Shared (aliased) containers are converted once, so alias expansion cannot blow up.
    """
    if memo is None:
        memo = {}
    if isinstance(value, dict | list) and id(value) in memo:
        return memo[id(value)]
    if isinstance(value, dict):
        out_map: dict[Any, Any] = {}
        memo[id(value)] = out_map
        for key, item in value.items():
            if isinstance(key, str):  # non-string keys are reported by _non_string_key_issues
                out_map[str(key)] = _to_plain(item, memo)
        return out_map
    if isinstance(value, list):
        out_list: list[Any] = []
        memo[id(value)] = out_list
        out_list.extend(_to_plain(item, memo) for item in value)
        return out_list
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        return str(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    return value


def _non_string_key_issues(raw: Any, file: Path) -> list[ManifestIssue]:
    """Report mapping keys that are not strings (e.g. ``1:``, ``null:``, ``true:``)."""
    issues: list[ManifestIssue] = []
    seen: set[int] = set()
    stack: list[tuple[Any, Loc]] = [(raw, ())]
    while stack:
        current, loc = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, CommentedMap):
            for key, item in current.items():
                if isinstance(key, str):
                    stack.append((item, (*loc, key)))
                    continue
                position = current.lc.data.get(key)
                line = position[0] + 1 if position else _container_line(current)
                issues.append(
                    ManifestIssue(file, line, _format_loc(loc), "mapping keys must be strings")
                )
        elif isinstance(current, CommentedSeq):
            stack.extend((item, (*loc, index)) for index, item in enumerate(current))
    return issues


# --------------------------------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------------------------------


def _container_line(container: Any) -> int | None:
    lc = getattr(container, "lc", None)
    line = getattr(lc, "line", None)
    return line + 1 if isinstance(line, int) else None


def _line_for(raw: Any, loc: Loc) -> int | None:
    """Line of the deepest part of ``loc`` present in ``raw`` (key line for maps, item for seqs)."""
    line = _container_line(raw)
    current = raw
    for part in loc:
        if (isinstance(current, CommentedMap) and isinstance(part, str) and part in current) or (
            isinstance(current, CommentedSeq) and isinstance(part, int) and 0 <= part < len(current)
        ):
            position = current.lc.data.get(part)
            if position:
                line = position[0] + 1
            current = current[part]
        else:
            # Missing key (e.g. "field required") or a pydantic-internal loc part: keep the
            # parent's line and try the remaining parts against the same container.
            continue
    return line


def _format_loc(loc: Loc) -> str | None:
    text = ""
    for part in loc:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += f".{part}" if text else part
    return text or None


def _message(error: ErrorDetails) -> str:
    kind = error["type"]
    if kind == "missing":
        return "field required"
    if kind == "extra_forbidden":
        return "unknown key (only keys starting with 'x-' may be added)"
    return str(error["msg"])


def _validation_issues(exc: ValidationError, raw: Any, file: Path) -> list[ManifestIssue]:
    return [
        ManifestIssue(
            file,
            _line_for(raw, tuple(error["loc"])),
            _format_loc(tuple(error["loc"])),
            _message(error),
        )
        for error in exc.errors(include_url=False, include_input=False)
    ]


def _raw_get(raw: Any, loc: Loc) -> Any:
    current = raw
    for part in loc:
        if isinstance(current, dict) and isinstance(part, str):
            current = current.get(part)
        elif isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
            current = current[part]
        else:
            return None
    return current


# --------------------------------------------------------------------------------------------------
# Filesystem checks
# --------------------------------------------------------------------------------------------------


def _check_path(
    *, root: Path, folder: Path, rel: str, want_dir: bool, container: str = "challenge folder"
) -> Path | str:
    """Check one referenced path: resolved path if usable, else the problem as a message."""
    target = folder / rel
    resolved = target.resolve()
    if not resolved.is_relative_to(root):
        return f"'{rel}' resolves outside the {container}"
    if not target.exists():
        return f"'{rel}' does not exist"
    if want_dir and not target.is_dir():
        return f"'{rel}' must be a directory"
    if not want_dir and not target.is_file():
        return f"'{rel}' must be a file"
    return resolved


def _relative_entries(directory: Path) -> tuple[set[str], set[str]]:
    """Relative POSIX paths of non-directory entries and of directories below ``directory``.

    Symlinks are not followed; a symlink counts as a file entry.
    """
    files: set[str] = set()
    dirs: set[str] = set()
    for current, dirnames, filenames in directory.walk(follow_symlinks=False):
        for name in list(dirnames):
            entry = current / name
            rel = entry.relative_to(directory).as_posix()
            if entry.is_symlink():
                files.add(rel)
                dirnames.remove(name)
            else:
                dirs.add(rel)
        for name in filenames:
            files.add((current / name).relative_to(directory).as_posix())
    return files, dirs


@dataclass(frozen=True)
class _MergeSource:
    label: str
    path: Path
    line: int | None
    field: str | None


def _clash_issues(sources: Iterable[_MergeSource], file: Path) -> list[ManifestIssue]:
    """Paths that would collide when checks are merged into the workspace root."""
    issues: list[ManifestIssue] = []
    seen: list[tuple[_MergeSource, set[str], set[str]]] = []
    for source in sources:
        files, dirs = _relative_entries(source.path)
        for earlier, earlier_files, earlier_dirs in seen:
            clashes = (files & earlier_files) | (files & earlier_dirs) | (dirs & earlier_files)
            for rel in sorted(clashes):
                issues.append(
                    ManifestIssue(
                        file,
                        source.line,
                        source.field,
                        f"'{rel}' exists in both {earlier.label} and {source.label}; "
                        "check files are merged into the workspace root and must not collide",
                    )
                )
        seen.append((source, files, dirs))
    return issues


def _relation(a: Path, b: Path) -> str | None:
    """How resolved path ``a`` relates to resolved path ``b``: same, inside, contains, or None."""
    if a == b:
        return "is the same path as"
    if a.is_relative_to(b):
        return "is inside"
    if b.is_relative_to(a):
        return "contains"
    return None


def _non_regular_entries(directory: Path) -> list[tuple[str, str]]:
    """``(relative POSIX path, kind)`` of every symlink or special file below ``directory``.

    Only names and kinds are reported, never contents; symlinks are not followed.
    """
    found: list[tuple[str, str]] = []
    for current, dirnames, filenames in directory.walk(follow_symlinks=False):
        dirnames.sort()
        for name in sorted([*dirnames, *filenames]):
            entry = current / name
            try:
                mode = entry.lstat().st_mode
            except OSError:
                continue
            if stat.S_ISDIR(mode) or stat.S_ISREG(mode):
                continue
            if stat.S_ISLNK(mode):
                kind = "a symlink"
                if name in dirnames:
                    dirnames.remove(name)
            elif stat.S_ISFIFO(mode):
                kind = "a FIFO"
            elif stat.S_ISSOCK(mode):
                kind = "a socket"
            elif stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
                kind = "a device file"
            else:
                kind = "a special file"
            found.append((entry.relative_to(directory).as_posix(), kind))
    return found


def _git_entries(directory: Path) -> list[str]:
    """Relative POSIX paths of every ``.git`` entry (any case, file or dir) below ``directory``.

    A ``.git`` directory is not descended into; symlinks are not followed.
    """
    found: list[str] = []
    for current, dirnames, filenames in directory.walk(follow_symlinks=False):
        dirnames.sort()
        for name in sorted([*dirnames, *filenames]):
            if name.casefold() != ".git":
                continue
            found.append((current / name).relative_to(directory).as_posix())
            if name in dirnames:
                dirnames.remove(name)
    return found


@dataclass(frozen=True)
class _Ref:
    """A resolved folder entry and where to report problems about it."""

    label: str
    path: Path
    file: Path
    line: int | None
    field: str | None

    def issue(self, message: str) -> ManifestIssue:
        return ManifestIssue(self.file, self.line, self.field, message)


def _isolation_issues(refs: dict[str, _Ref]) -> list[ManifestIssue]:
    """Enforce that solution and hidden checks can never reach the workspace or the image.

    Everything under ``workspace/`` and ``checks.visible`` is copied into the user's workspace,
    and the Dockerfile's folder is the build context sent into the image the sessions run. So
    ``solution`` and ``checks.hidden`` must not overlap the workspace or visible checks, visible
    checks must not overlap the workspace, and the build context must be a separate folder.
    """
    issues: list[ManifestIssue] = []
    workspace = refs.get("workspace")
    visible = refs.get("visible")
    for secret_key in ("hidden", "solution"):
        secret = refs.get(secret_key)
        if secret is None:
            continue
        for exposed in (workspace, visible):
            if exposed is None:
                continue
            relation = _relation(secret.path, exposed.path)
            if relation is None:
                continue
            # Blame checks.visible when it covers the secret; otherwise the secret's own field.
            blame_exposed = exposed.field is not None and relation != "contains"
            blamed, other = (exposed, secret) if blame_exposed else (secret, exposed)
            issues.append(
                blamed.issue(
                    f"{blamed.label} {_relation(blamed.path, other.path)} {other.label}; "
                    f"{secret.label} must never be copied into the workspace, "
                    "keep them in separate folders"
                )
            )
    if workspace is not None and visible is not None:
        relation = _relation(visible.path, workspace.path)
        if relation is not None:
            issues.append(
                visible.issue(
                    f"{visible.label} {relation} {workspace.label}; visible checks must be a "
                    "separate folder that is merged into the workspace"
                )
            )
    dockerfile = refs.get("dockerfile")
    if dockerfile is not None:
        context = dockerfile.path.parent
        for key in ("workspace", "hidden", "solution"):
            leaked = refs.get(key)
            if leaked is None:
                continue
            leaks = leaked.path.is_relative_to(context)
            if key == "hidden":  # a context inside the hidden checks ships some of them too
                leaks = leaks or context.is_relative_to(leaked.path)
            if leaks:
                issues.append(
                    dockerfile.issue(
                        f"the Dockerfile's folder (the build context) "
                        f"{_relation(context, leaked.path)} {leaked.label}; the build context goes "
                        "into the image, so it must be a separate folder such as environment/"
                    )
                )
    return issues


def _challenge_fs_issues(folder: Path, root: Path, manifest: Path, raw: Any) -> list[ManifestIssue]:
    issues: list[ManifestIssue] = []

    # Required entries that are not referenced from the manifest.
    ticket = _check_path(root=root, folder=folder, rel=TICKET_FILE, want_dir=False)
    if isinstance(ticket, str):
        issues.append(ManifestIssue(folder / TICKET_FILE, None, None, ticket))
    workspace = _check_path(root=root, folder=folder, rel=WORKSPACE_DIR, want_dir=True)
    if isinstance(workspace, str):
        issues.append(ManifestIssue(folder / WORKSPACE_DIR, None, None, workspace))

    if raw is None:
        return issues

    folder_name = _normalized(folder).name
    challenge_id = _raw_get(raw, ("id",))
    if isinstance(challenge_id, str) and challenge_id != folder_name:
        issues.append(
            ManifestIssue(
                manifest,
                _line_for(raw, ("id",)),
                "id",
                f"id '{challenge_id}' must match the folder name '{folder_name}'",
            )
        )

    references: list[tuple[Loc, bool]] = [
        (("environment", "dockerfile"), False),
        (("checks", "visible"), True),
        (("checks", "hidden"), True),
        (("solution",), False),
        (("debrief", "questions"), False),
    ]
    resolved: dict[Loc, Path] = {}
    for loc, want_dir in references:
        value = _raw_get(raw, loc)
        # Values the model rejects (wrong type, absolute, escaping) are reported by the model.
        if not isinstance(value, str) or relative_path_problem(value) is not None:
            continue
        target = _check_path(root=root, folder=folder, rel=value, want_dir=want_dir)
        if isinstance(target, str):
            issues.append(ManifestIssue(manifest, _line_for(raw, loc), _format_loc(loc), target))
        else:
            resolved[loc] = target

    refs: dict[str, _Ref] = {}
    if isinstance(workspace, Path):
        refs["workspace"] = _Ref(f"{WORKSPACE_DIR}/", workspace, folder / WORKSPACE_DIR, None, None)
    for key, loc in (
        ("dockerfile", ("environment", "dockerfile")),
        ("visible", ("checks", "visible")),
        ("hidden", ("checks", "hidden")),
        ("solution", ("solution",)),
    ):
        if loc in resolved:
            field = str(_format_loc(loc))
            refs[key] = _Ref(field, resolved[loc], manifest, _line_for(raw, loc), field)

    isolation = _isolation_issues(refs)
    issues.extend(isolation)

    for key in ("workspace", "visible", "hidden"):
        ref = refs.get(key)
        if ref is None:
            continue
        for rel in _git_entries(ref.path):
            shown = (ref.path / rel).relative_to(root).as_posix()
            issues.append(
                ref.issue(
                    f"'{shown}' is a git repository or git file; challenges must not ship .git"
                )
            )
        for rel, kind in _non_regular_entries(ref.path):
            shown = (ref.path / rel).relative_to(root).as_posix()
            issues.append(
                ref.issue(
                    f"'{shown}' is {kind}; {ref.label} may only contain regular files "
                    "and directories"
                )
            )

    if not isolation:  # overlapping folders would only repeat the same problem as clashes
        sources = [
            _MergeSource(ref.label, ref.path, ref.line, ref.field)
            for key in ("workspace", "visible", "hidden")
            if (ref := refs.get(key)) is not None
        ]
        issues.extend(_clash_issues(sources, manifest))
    return issues


def _pack_fs_issues(folder: Path, root: Path, manifest: Path, raw: Any) -> list[ManifestIssue]:
    issues: list[ManifestIssue] = []
    challenges = _raw_get(raw, ("challenges",))
    if not isinstance(challenges, list):
        return issues
    for index, name in enumerate(challenges):
        if not isinstance(name, str) or not re.fullmatch(SLUG_PATTERN, name):
            continue  # reported by the model
        loc: Loc = ("challenges", index)
        target = _check_path(
            root=root, folder=folder, rel=name, want_dir=True, container="pack folder"
        )
        if isinstance(target, str):
            message = f"challenge folder {target}"
            issues.append(ManifestIssue(manifest, _line_for(raw, loc), _format_loc(loc), message))
    return issues


# --------------------------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------------------------


def _sorted(issues: list[ManifestIssue]) -> list[ManifestIssue]:
    # Stable: issues without a line keep their discovery order after the located ones of a file.
    return sorted(issues, key=lambda issue: (issue.line is None, issue.line or 0))


def load_challenge(folder: Path) -> Challenge:
    """Load and validate the challenge in ``folder``.

    Raises ``ManifestError`` listing every problem found.
    """
    folder = Path(folder)
    manifest_path = folder / CHALLENGE_MANIFEST
    if not manifest_path.is_file():
        raise ManifestError(
            [ManifestIssue(manifest_path, None, None, f"{CHALLENGE_MANIFEST} not found")]
        )
    root = folder.resolve()

    issues: list[ManifestIssue] = []
    raw = _parse_yaml(manifest_path, issues)
    model: ChallengeManifest | None = None
    if raw is not None:
        issues.extend(_non_string_key_issues(raw, manifest_path))
        try:
            model = ChallengeManifest.model_validate(_to_plain(raw))
        except ValidationError as exc:
            issues.extend(_validation_issues(exc, raw, manifest_path))
    issues.extend(_challenge_fs_issues(folder, root, manifest_path, raw))

    if issues or model is None:
        raise ManifestError(_sorted(issues))
    return Challenge(root=root, manifest_path=root / CHALLENGE_MANIFEST, manifest=model)


def load_pack(folder: Path) -> Pack:
    """Load and validate the pack in ``folder``.

    Raises ``ManifestError`` listing every problem found.
    """
    folder = Path(folder)
    manifest_path = folder / PACK_MANIFEST
    if not manifest_path.is_file():
        raise ManifestError(
            [ManifestIssue(manifest_path, None, None, f"{PACK_MANIFEST} not found")]
        )
    root = folder.resolve()

    issues: list[ManifestIssue] = []
    raw = _parse_yaml(manifest_path, issues)
    model: PackManifest | None = None
    if raw is not None:
        issues.extend(_non_string_key_issues(raw, manifest_path))
        try:
            model = PackManifest.model_validate(_to_plain(raw))
        except ValidationError as exc:
            issues.extend(_validation_issues(exc, raw, manifest_path))
        issues.extend(_pack_fs_issues(folder, root, manifest_path, raw))

    if issues or model is None:
        raise ManifestError(_sorted(issues))
    return Pack(root=root, manifest_path=root / PACK_MANIFEST, manifest=model)
