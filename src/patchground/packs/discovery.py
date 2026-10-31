"""Local challenge discovery for ``list`` and ``show``: read-only metadata, never execution.

Discovery looks at a directory the user names (default: the current one) and its *immediate*
children only. A child is a candidate when it contains a ``challenge.yaml`` entry. Each candidate is
validated with :func:`patchground.spec.load_challenge`; valid ones become summaries and invalid ones
are reported with their problems instead of being hidden. Symlinked children are reported but never
followed. Nothing is built, run, installed, remembered, or granted trust here.

The output never contains the reference solution, hidden checks, hints text, or the test command:
only manifest metadata and, for ``show``, the ticket the user would see anyway.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from patchground.spec import (
    AIPolicy,
    ChallengeManifest,
    ChallengeType,
    Difficulty,
    ManifestError,
    load_challenge,
)

CHALLENGE_MANIFEST = "challenge.yaml"
TICKET_FILE = "TICKET.md"
MAX_TICKET_BYTES = 256 * 1024
"""Tickets are short prose; anything larger is reported instead of read."""


class DiscoveryError(Exception):
    """The requested directory or path cannot be examined at all (an environment problem)."""


class _Result(BaseModel):
    model_config = ConfigDict(frozen=True)


class DiscoveryFilters(_Result):
    """Optional ``list`` filters; all given filters must match (AND). Text matches ignore case."""

    type: ChallengeType | None = None
    lang: str | None = None
    difficulty: Difficulty | None = None
    tag: str | None = None

    def matches(self, manifest: ChallengeManifest) -> bool:
        if self.type is not None and manifest.type is not self.type:
            return False
        if self.difficulty is not None and manifest.difficulty is not self.difficulty:
            return False
        if self.lang is not None and not _contains(manifest.languages, self.lang):
            return False
        return self.tag is None or _contains(manifest.tags, self.tag)


class ChallengeSummary(_Result):
    """Public metadata of one valid challenge."""

    id: str
    path: str
    title: str
    version: str
    type: ChallengeType
    summary: str
    languages: tuple[str, ...]
    tags: tuple[str, ...]
    difficulty: Difficulty
    timebox_minutes: int
    ai_policy: AIPolicy


class InvalidChallenge(_Result):
    """A candidate folder that could not be loaded; ``issues`` are file:line problems."""

    name: str
    path: str
    issues: tuple[str, ...]


class DiscoveryResult(_Result):
    """Result of ``list``: valid matches plus every invalid candidate (filters never hide them)."""

    directory: str
    filters: DiscoveryFilters
    challenges: tuple[ChallengeSummary, ...]
    invalid: tuple[InvalidChallenge, ...]


class ChallengeDetails(_Result):
    """Result of ``show``: metadata and ticket when valid, problems otherwise."""

    path: str
    valid: bool
    challenge: ChallengeSummary | None = None
    author: str | None = None
    content_license: str | None = None
    provenance: str | None = None
    hint_count: int | None = None
    services: tuple[str, ...] = ()
    ticket: str | None = None
    issues: tuple[str, ...] = ()


def _contains(values: Iterable[str], wanted: str) -> bool:
    folded = wanted.strip().casefold()
    return any(value.casefold() == folded for value in values)


def _summary(manifest: ChallengeManifest, shown: str) -> ChallengeSummary:
    return ChallengeSummary(
        id=manifest.id,
        path=shown,
        title=manifest.title,
        version=manifest.version,
        type=manifest.type,
        summary=manifest.summary,
        languages=tuple(manifest.languages),
        tags=tuple(manifest.tags),
        difficulty=manifest.difficulty,
        timebox_minutes=manifest.timebox_minutes,
        ai_policy=manifest.ai_policy,
    )


def _regular_file_problem(folder: Path, name: str) -> str | None:
    """Why ``folder/name`` is not a plain regular file (symlinks are not followed)."""
    try:
        mode = (folder / name).lstat().st_mode
    except FileNotFoundError:
        return f"{name}: not found"
    except OSError:
        return f"{name}: cannot be read"
    if stat.S_ISLNK(mode):
        return f"{name}: is a symlink; challenge files must be regular files"
    if not stat.S_ISREG(mode):
        return f"{name}: must be a regular file"
    return None


def _load(folder: Path) -> tuple[ChallengeManifest | None, tuple[str, ...]]:
    """Validate ``folder`` without executing anything. Returns the manifest or its problems."""
    for name in (CHALLENGE_MANIFEST, TICKET_FILE):
        problem = _regular_file_problem(folder, name)
        if problem is not None:
            return None, (problem,)
    try:
        challenge = load_challenge(folder)
    except ManifestError as exc:
        return None, tuple(
            f"{issue.file.name}:{issue.line or 1}: invalid challenge manifest or layout"
            for issue in exc.issues
        )
    except OSError:
        return None, ("challenge folder cannot be read",)
    return challenge.manifest, ()


def _read_ticket(folder: Path) -> tuple[str | None, str | None]:
    """Read ``TICKET.md`` without following a symlink; returns ``(text, problem)``."""
    path = folder / TICKET_FILE
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(path, flags)
    except OSError:
        return None, f"{TICKET_FILE}: cannot be read safely"
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return None, f"{TICKET_FILE}: must be a regular file"
        if info.st_size > MAX_TICKET_BYTES:
            return None, f"{TICKET_FILE}: larger than {MAX_TICKET_BYTES} bytes"
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            data = handle.read(MAX_TICKET_BYTES + 1)
    except OSError:
        return None, f"{TICKET_FILE}: cannot be read"
    finally:
        if fd >= 0:
            os.close(fd)
    if len(data) > MAX_TICKET_BYTES:
        return None, f"{TICKET_FILE}: larger than {MAX_TICKET_BYTES} bytes"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, f"{TICKET_FILE}: not valid UTF-8"


def _require_directory(path: Path, what: str) -> None:
    try:
        is_dir = path.is_dir()
    except OSError:
        is_dir = False
    if not is_dir:
        raise DiscoveryError(f"{what} '{path}' does not exist or is not a directory")


def discover_challenges(
    directory: Path | None = None, filters: DiscoveryFilters | None = None
) -> DiscoveryResult:
    """List challenge folders directly inside ``directory`` (default: the current directory).

    Only immediate children are examined; nothing is followed recursively. A symlinked child is
    reported as invalid when it points at a folder, and never read through. Raises
    ``DiscoveryError`` when ``directory`` itself is missing, not a directory, or unreadable.
    """
    base = Path(directory) if directory is not None else Path()
    active = filters or DiscoveryFilters()
    _require_directory(base, "directory")
    try:
        entries = sorted(os.scandir(base), key=lambda entry: entry.name)
    except OSError as exc:
        raise DiscoveryError(f"directory '{base}' cannot be read") from exc

    challenges: list[ChallengeSummary] = []
    invalid: list[InvalidChallenge] = []
    for entry in entries:
        child = base / entry.name
        shown = str(child)
        try:
            if entry.is_symlink():
                if entry.is_dir(follow_symlinks=True):
                    invalid.append(
                        InvalidChallenge(
                            name=entry.name,
                            path=shown,
                            issues=("is a symlink; discovery does not follow symlinked folders",),
                        )
                    )
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
            os.lstat(child / CHALLENGE_MANIFEST)
        except FileNotFoundError:
            continue
        except OSError:
            invalid.append(
                InvalidChallenge(name=entry.name, path=shown, issues=("folder cannot be read",))
            )
            continue
        manifest, issues = _load(child)
        if manifest is None:
            invalid.append(InvalidChallenge(name=entry.name, path=shown, issues=issues))
        elif active.matches(manifest):
            challenges.append(_summary(manifest, shown))
    return DiscoveryResult(
        directory=str(base),
        filters=active,
        challenges=tuple(challenges),
        invalid=tuple(invalid),
    )


def show_challenge(path: Path) -> ChallengeDetails:
    """Describe one local challenge folder: safe metadata and its ticket, never secrets.

    Invalid folders yield ``valid=False`` with their problems. Raises ``DiscoveryError`` when
    ``path`` is missing or not a directory.
    """
    folder = Path(path)
    _require_directory(folder, "challenge folder")
    shown = str(folder)
    manifest, issues = _load(folder)
    if manifest is None:
        return ChallengeDetails(path=shown, valid=False, issues=issues)
    ticket, problem = _read_ticket(folder)
    if problem is not None:
        return ChallengeDetails(path=shown, valid=False, issues=(problem,))
    return ChallengeDetails(
        path=shown,
        valid=True,
        challenge=_summary(manifest, shown),
        author=manifest.author.name,
        content_license=manifest.content_license,
        provenance=manifest.provenance.value,
        hint_count=len(manifest.hints),
        services=tuple(manifest.environment.services),
        ticket=ticket,
    )
