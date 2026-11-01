"""Reference resolution, installed discovery and consent-gated execution preparation.

Local paths stay untouched. Anything that resolves into managed storage — by id or by path — is a
pack version and is gated: its bytes are captured into a private temporary copy, verified against
the registered digest, reviewed from that very copy, and only then handed out.
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from patchground.packs.builtin import builtin_challenge
from patchground.packs.discovery import (
    ChallengeDetails,
    ChallengeSummary,
    DiscoveryFilters,
    DiscoveryResult,
    InvalidChallenge,
    discover_challenges,
    show_challenge,
)
from patchground.packs.models import (
    ConsentRequired,
    ExecutionRecipe,
    PackError,
    PackIdentity,
    PackReview,
    PreparedChallenge,
    ResolvedChallenge,
)
from patchground.packs.store import (
    Entry,
    Version,
    cache_path,
    cache_problem,
    capture_tree,
    identity_of,
    load_state,
    locked,
    packs_dir,
    read_limited,
    remove_tree,
    save_state,
    state_root,
)
from patchground.safeio import safe_path
from patchground.spec import ManifestError, PackManifest, load_challenge, load_pack
from patchground.spec.models import SLUG_PATTERN

MAX_RECIPE_BYTES = 64 * 1024
MAX_REVIEW_BYTES = 1024 * 1024
"""Whole-pack recipe review bound; exceeding it fails the operation, never truncates."""
"""Anything longer cannot be shown in full, so such a pack is refused rather than half-reviewed."""
_SLUG = SLUG_PATTERN.removeprefix("^").removesuffix("$")
_QUALIFIED = re.compile(rf"(?P<pack>{_SLUG}):(?P<id>{_SLUG})")
_CACHE_NAME = re.compile(r"(.+)@([0-9a-f]{40}|[0-9a-f]{64})")


class InstalledChallengeSummary(ChallengeSummary):
    pack: PackIdentity
    reference: str
    """Unambiguous ``pack:challenge`` form accepted by ``resolve_challenge``."""


class InstalledDiscoveryResult(DiscoveryResult):
    challenges: tuple[InstalledChallengeSummary, ...]


@dataclass(frozen=True)
class Inspection:
    manifest: PackManifest
    recipes: tuple[ExecutionRecipe, ...]
    summaries: tuple[ChallengeSummary, ...]


def _describe(exc: ManifestError, folder: Path, prefix: str = "") -> str:
    parts = []
    for issue in exc.issues[:5]:
        try:
            shown = os.path.relpath(issue.file, folder)
        except ValueError:
            shown = issue.file.name
        parts.append(f"{prefix}{shown}:{issue.line or 1}: invalid manifest or layout")
    return "; ".join(parts) or "invalid pack"


def read_recipes(pack_root: Path, challenges: Iterable[str]) -> tuple[ExecutionRecipe, ...]:
    """Complete build/run recipes of each indexed challenge, read from ``pack_root``."""
    recipes = []
    reviewed = 0
    for name in challenges:
        folder = pack_root / name
        try:
            manifest = load_challenge(folder).manifest
        except ManifestError as exc:
            raise PackError(_describe(exc, folder, f"{name}/")) from None
        env = manifest.environment
        try:
            dockerfile = read_limited(folder / env.dockerfile, MAX_RECIPE_BYTES).decode()
        except (UnicodeDecodeError, OSError) as exc:
            raise PackError(f"{name}: Dockerfile cannot be reviewed in full") from exc
        if len(env.test_command.encode()) > MAX_RECIPE_BYTES:
            raise PackError(f"{name}: test command cannot be reviewed in full")
        reviewed += len(dockerfile) + len(env.test_command) + sum(map(len, env.services))
        if reviewed > MAX_REVIEW_BYTES:
            raise PackError("pack recipes are too large to review in full")
        recipes.append(
            ExecutionRecipe(
                challenge_id=name,
                dockerfile_path=env.dockerfile,
                dockerfile=dockerfile,
                services=tuple(env.services),
                command=env.test_command,
            )
        )
    return tuple(recipes)


def inspect_pack(folder: Path) -> Inspection:
    """Structurally validate a captured pack and every indexed challenge; nothing is executed."""
    try:
        pack = load_pack(folder)
    except ManifestError as exc:
        raise PackError(_describe(exc, folder)) from None
    names = tuple(pack.manifest.challenges)
    recipes = read_recipes(folder, names)
    for name in names:
        if load_challenge(folder / name).manifest.id != name:
            raise PackError(f"{name}: challenge id must equal its folder name")
    found = {c.id: c for c in discover_challenges(folder).challenges}
    missing = [name for name in names if name not in found]
    if missing:
        raise PackError(f"{missing[0]}: challenge folder is not a valid challenge")
    return Inspection(pack.manifest, recipes, tuple(found[name] for name in names))


def make_review(
    identity: PackIdentity,
    recipes: tuple[ExecutionRecipe, ...],
    previous: Version | None = None,
    folders: dict[str, str] | None = None,
) -> PackReview:
    if previous is None or folders is None:
        return PackReview(pack=identity, recipes=recipes)
    old, new = previous.folders, folders
    return PackReview(
        pack=identity,
        recipes=recipes,
        previous_commit=previous.commit,
        added=tuple(sorted(set(new) - set(old))),
        removed=tuple(sorted(set(old) - set(new))),
        changed=tuple(sorted(n for n in set(old) & set(new) if old[n] != new[n])),
    )


# --------------------------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Managed:
    name: str
    entry: Entry
    version: Version
    challenge: str


def _managed(name: str, entry: Entry, commit: str, challenge: str) -> _Managed:
    version = entry.versions.get(commit)
    if version is None or challenge not in version.folders:
        raise PackError("path is not a registered installed challenge")
    return _Managed(name, entry, version, challenge)


def _installed(packs: dict[str, Entry], name: str | None, challenge: str) -> _Managed:
    if name is not None:
        entry = packs.get(name)
        if entry is None:
            raise PackError(f"pack '{name}' is not installed")
        return _managed(name, entry, entry.active, challenge)
    found = [(n, e) for n, e in sorted(packs.items()) if challenge in e.versions[e.active].folders]
    if not found:
        raise _NotInstalled
    if len(found) > 1:
        options = ", ".join(f"{n}:{challenge}" for n, _ in found)
        raise PackError(f"challenge '{challenge}' is ambiguous; use one of: {options}")
    n, e = found[0]
    return _managed(n, e, e.active, challenge)


class _NotInstalled(Exception):
    pass


def _managed_rel(candidate: Path, root: Path) -> tuple[str, ...] | None:
    """Parts below the pack cache when ``candidate`` lies in it, even if the cache is absent.

    The lexical test needs no existing directory (a missing cache must not turn a managed-looking
    path into a trusted local one); the identity test catches links and case-insensitive aliases.
    """
    base = packs_dir(root)
    real = Path(os.path.realpath(candidate))
    if real.is_relative_to(base):
        return real.relative_to(base).parts
    if base.is_dir():
        for ancestor in (real, *real.parents):
            try:
                if ancestor.exists() and ancestor.samefile(base):
                    return real.parts[len(ancestor.parts) :]
            except OSError:
                continue
    return None


def _by_path(candidate: Path, root: Path) -> _Managed | None:
    rel = _managed_rel(candidate, root)
    if rel is None:
        return None
    match = _CACHE_NAME.fullmatch(rel[0]) if rel else None
    if match is None or len(rel) != 2:
        raise PackError("path inside managed pack storage is not an installed challenge")
    entry = load_state(root).packs.get(match.group(1))
    if entry is None:
        raise PackError("path inside managed pack storage is not registered")
    return _managed(match.group(1), entry, match.group(2), rel[1])


def _locate(reference: str | Path, root: Path) -> Path | _Managed:
    if isinstance(reference, str):
        qualified = _QUALIFIED.fullmatch(reference)
        if qualified:
            packs = load_state(root).packs
            return _installed(dict(packs), qualified["pack"], qualified["id"])
        candidate = Path(reference)
        # An existing local folder keeps its old meaning; ids are only for names not on disk.
        if not (candidate.exists() or candidate.is_symlink()) and re.fullmatch(
            SLUG_PATTERN, reference
        ):
            try:
                return _installed(dict(load_state(root).packs), None, reference)
            except _NotInstalled:
                bundled = builtin_challenge(reference)
                if bundled is not None:
                    return bundled
    else:
        candidate = reference
    return _by_path(candidate, root) or candidate


def _pack_dir(root: Path, target: _Managed) -> Path:
    path = cache_path(root, target.name, target.version.commit)
    try:
        safe_path(path, directory=True, error=PackError, label="installed pack")
    except OSError as exc:
        raise PackError("installed pack content is missing") from exc
    return path


def resolve_challenge(reference: str | Path, *, root: Path | None = None) -> ResolvedChallenge:
    """Resolve an id, ``pack:id`` or path. Resolution alone never grants consent."""
    base = state_root(root)
    target = _locate(reference, base)
    if isinstance(target, Path):
        return ResolvedChallenge(path=target)
    return ResolvedChallenge(
        path=_pack_dir(base, target) / target.challenge,
        pack=identity_of(target.name, target.entry, target.version),
    )


def discover_installed(
    filters: DiscoveryFilters | None = None, *, root: Path | None = None
) -> InstalledDiscoveryResult:
    """Challenges of active pack versions from validated catalog metadata. Cache bytes are only
    hashed to flag tampered or missing packs; nothing is built, executed or initialized."""
    base = state_root(root)
    active = filters or DiscoveryFilters()
    found: list[InstalledChallengeSummary] = []
    invalid: list[InvalidChallenge] = []
    for name, entry in sorted(load_state(base).packs.items()):
        version = entry.versions[entry.active]
        pack = identity_of(name, entry, version)
        folder = cache_path(base, name, version.commit)
        problem = cache_problem(base, name, version)
        if problem is not None:
            invalid.append(InvalidChallenge(name=name, path=str(folder), issues=(problem,)))
            continue
        for summary in version.challenges:
            if _matches(active, summary):
                found.append(
                    InstalledChallengeSummary(
                        **summary.model_copy(
                            update={"path": str(folder / summary.id)}
                        ).model_dump(),
                        pack=pack,
                        reference=f"{name}:{summary.id}",
                    )
                )
    return InstalledDiscoveryResult(
        directory=str(packs_dir(base)),
        filters=active,
        challenges=tuple(found),
        invalid=tuple(invalid),
    )


def _matches(filters: DiscoveryFilters, summary: ChallengeSummary) -> bool:
    def has(values: Iterable[str], wanted: str) -> bool:
        return any(v.casefold() == wanted.strip().casefold() for v in values)

    return (
        (filters.type is None or summary.type is filters.type)
        and (filters.difficulty is None or summary.difficulty is filters.difficulty)
        and (filters.lang is None or has(summary.languages, filters.lang))
        and (filters.tag is None or has(summary.tags, filters.tag))
    )


# --------------------------------------------------------------------------------------------
# Preparation
# --------------------------------------------------------------------------------------------


def _grant(root: Path, target: _Managed) -> None:
    with locked(root):
        state = load_state(root)
        entry = state.packs.get(target.name)
        current = entry.versions.get(target.version.commit) if entry else None
        if entry is None or current is None or current.identity != target.version.identity:
            raise PackError("pack changed while consent was being recorded")
        versions = {
            **entry.versions,
            current.commit: current.model_copy(update={"consented": True}),
        }
        packs = {**state.packs, target.name: entry.model_copy(update={"versions": versions})}
        save_state(root, state.model_copy(update={"packs": packs}))


@contextmanager
def _verified_copy(root: Path, target: _Managed) -> Iterator[tuple[Path, Path]]:
    """Capture an installed pack into a private temporary copy and verify it against the catalog.

    Yields ``(copy, canonical_cache_dir)``; the single place where cache bytes are trusted.
    """
    source = _pack_dir(root, target)
    temp = Path(tempfile.mkdtemp(prefix="patchground-pack-")).resolve()
    try:
        copy = temp / "pack"
        copy.mkdir(mode=0o700)
        if capture_tree(source, copy, seal=False).digest != target.version.digest:
            raise PackError("installed pack content failed integrity verification")
        yield copy, source
    finally:
        remove_tree(temp)


def show_reference(reference: str | Path, *, root: Path | None = None) -> ChallengeDetails:
    """Describe a challenge for ``show``. Installed content is read from a verified temporary
    copy, needs no consent (nothing is built or run) and is reported under canonical paths."""
    base = state_root(root)
    target = _locate(reference, base)
    if isinstance(target, Path):
        return show_challenge(target)
    with _verified_copy(base, target) as (copy, source):
        details = show_challenge(copy / target.challenge)
        shown = str(source / target.challenge)
        challenge = (
            details.challenge.model_copy(update={"path": shown}) if details.challenge else None
        )
        return details.model_copy(update={"path": shown, "challenge": challenge})


@contextmanager
def prepare_execution(
    reference: str | Path,
    *,
    yes: bool = False,
    expected_identity: str | None = None,
    root: Path | None = None,
) -> Iterator[PreparedChallenge]:
    """Gate and prepare a challenge for build/run.

    Local paths pass through unchanged. Installed content is captured into a private temporary
    copy, verified against the registered digest, and reviewed from that copy. Without consent for
    this exact identity ``ConsentRequired`` is raised before anything is built; ``yes`` records
    consent. ``expected_identity`` fails closed if the version differs from what was reviewed.
    """
    base = state_root(root)
    target = _locate(reference, base)
    if isinstance(target, Path):
        if expected_identity is not None:
            raise PackError("expected identity does not apply to a local challenge")
        yield PreparedChallenge(path=target, source_path=target)
        return

    version = target.version
    pack = identity_of(target.name, target.entry, version)
    with _verified_copy(base, target) as (copy, source):
        if expected_identity is not None and expected_identity != version.identity:
            raise PackError("pack identity differs from the reviewed version")
        if not version.consented:
            review = make_review(pack, read_recipes(copy, version.folders))
            if not yes:
                raise ConsentRequired(review)
            _grant(base, target)
        # The original local source must also be excluded when selecting a Git executable.
        origin = (Path(pack.source),) if pack.source_kind == "local" else ()
        yield PreparedChallenge(
            path=copy / target.challenge,
            source_path=source / target.challenge,
            pack=pack,
            input_roots=(copy, source, *origin),
        )
