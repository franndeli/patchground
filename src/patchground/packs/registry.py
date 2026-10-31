"""Installed pack lifecycle: add, list, update and remove, plus re-exported resolution APIs.

Installation only fetches, copies and structurally validates; it never builds or runs. Content is
captured once (hashed while copied), validated in that captured copy and published atomically into
the immutable cache, then the catalog is replaced atomically. A failure at any point leaves the
previous catalog and active version untouched.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from patchground.packs.execution import (
    Inspection,
    InstalledChallengeSummary,
    InstalledDiscoveryResult,
    discover_installed,
    inspect_pack,
    make_review,
    prepare_execution,
    resolve_challenge,
    show_reference,
)
from patchground.packs.models import (
    ConsentRequired,
    PackError,
    PackInfo,
    PackListing,
    PackProblem,
    PackRemoval,
    PackUpdateResult,
    SourceSnapshot,
)
from patchground.packs.source import fetch_pack
from patchground.packs.store import (
    Capture,
    Entry,
    PublishedStateError,
    State,
    Version,
    cache_path,
    cache_problem,
    capture_tree,
    ensure_dirs,
    hold_stage,
    identity_of,
    load_state,
    locked,
    make_identity,
    packs_dir,
    remove_tree,
    save_state,
    state_root,
)
from patchground.safeio import open_directory

__all__ = [
    "InstalledChallengeSummary",
    "InstalledDiscoveryResult",
    "add_pack",
    "discover_installed",
    "list_packs",
    "prepare_execution",
    "remove_pack",
    "resolve_challenge",
    "show_reference",
    "update_pack",
]


class _Staged:
    """A fetched revision captured into a private stage and validated, not yet published."""

    def __init__(
        self,
        snap: SourceSnapshot,
        path: Path,
        identity: tuple[int, int],
        capture: Capture,
        inspection: Inspection,
    ):
        self.snap = snap
        self.path = path
        self.filesystem_identity = identity
        self.capture = capture
        self.inspection = inspection
        self.name = inspection.manifest.name
        self.version = Version(
            version=inspection.manifest.version,
            commit=snap.commit,
            digest=capture.digest,
            identity=make_identity(
                self.name,
                inspection.manifest.version,
                snap.source_kind,
                snap.source,
                snap.commit,
                capture.digest,
            ),
            challenges=tuple(s.model_copy(update={"path": s.id}) for s in inspection.summaries),
            folders=capture.folder_digests(tuple(s.id for s in inspection.summaries)),
        )


@contextmanager
def _stage(source: str | Path, ref: str, root: Path) -> Iterator[_Staged]:
    with fetch_pack(source, ref) as snap:
        ensure_dirs(root)
        path = Path(tempfile.mkdtemp(prefix=".stage-", dir=packs_dir(root))).resolve()
        # The descriptor stays open until cleanup is done, so the identity cannot be recycled.
        with hold_stage(path) as identity:
            try:
                capture = capture_tree(snap.path.resolve(), path, seal=True)
                yield _Staged(snap, path, identity, capture, inspect_pack(path))
            finally:
                # Only the directory created here: a replacement at this path is not ours to delete.
                remove_tree(path, expect=identity)


def _publish(root: Path, staged: _Staged, entry: Entry | None) -> bool:
    """Place the staged tree in the cache (caller holds the lock); True when newly created.

    An existing destination is never deleted or replaced. It is accepted only when its actual
    bytes match what would be published (registered or not, e.g. after an interrupted add);
    anything else fails closed.
    """
    final = cache_path(root, staged.name, staged.snap.commit)
    if final.exists() or final.is_symlink():
        known = entry.versions.get(staged.snap.commit) if entry is not None else None
        if known is not None and cache_problem(root, staged.name, known) is not None:
            raise PackError("registered pack cache failed integrity verification")
        try:
            actual = capture_tree(final, None, seal=False).digest
        except PackError:
            actual = None
        if actual != staged.version.digest or (known and known.digest != actual):
            raise PackError("pack cache destination exists with different content; not replaced")
        return False
    try:
        # The stage must still be exactly what was validated, not something swapped in since.
        if capture_tree(staged.path, None, seal=False).digest != staged.version.digest:
            raise PackError("staged pack changed before publication")
        staged.path.rename(final)
        with open_directory(final.parent, error=PackError, label="pack cache") as directory:
            os.fsync(directory)
    except OSError as exc:
        raise PackError("pack could not be published") from exc
    return True


def _info(root: Path, name: str, entry: Entry, commit: str) -> PackInfo:
    ver = entry.versions[commit]
    return PackInfo(
        pack=identity_of(name, entry, ver),
        path=cache_path(root, name, commit),
        ref=entry.ref,
        consented=ver.consented,
        active=commit == entry.active,
    )


def add_pack(source: str | Path, *, ref: str = "HEAD", root: Path | None = None) -> PackInfo:
    """Install a pack at an exact commit. Idempotent; never replaces an existing installation."""
    base = state_root(root)
    with _stage(source, ref, base) as staged, locked(base):
        state = load_state(base)
        entry = state.packs.get(staged.name)
        if entry is not None:
            if entry.source != staged.snap.source:
                raise PackError(f"pack '{staged.name}' is already installed from another source")
            if staged.snap.commit not in entry.versions:
                raise PackError(
                    f"pack '{staged.name}' is already installed at another revision; "
                    "use pack update"
                )
            _publish(base, staged, entry)  # verifies identical content
            return _info(base, staged.name, entry, staged.snap.commit)
        created = _publish(base, staged, None)
        new = Entry(
            source=staged.snap.source,
            source_kind=staged.snap.source_kind,
            ref=ref,
            active=staged.snap.commit,
            versions={staged.snap.commit: staged.version},
        )
        updated = State(packs={**state.packs, staged.name: new})
        try:
            save_state(base, updated)
        except PackError as exc:
            if created and not isinstance(exc, PublishedStateError):
                remove_tree(
                    cache_path(base, staged.name, staged.snap.commit),
                    expect=staged.filesystem_identity,
                )
            raise
        return _info(base, staged.name, new, staged.snap.commit)


def list_packs(*, root: Path | None = None) -> PackListing:
    """Every registered cached version. Reads only; missing state is an empty listing."""
    base = state_root(root)
    packs: list[PackInfo] = []
    invalid: list[PackProblem] = []
    for name, entry in sorted(load_state(base).packs.items()):
        for commit in entry.versions:
            problem = cache_problem(base, name, entry.versions[commit])
            if problem is not None:
                invalid.append(PackProblem(name=f"{name}@{commit[:12]}", reason=problem))
                continue
            packs.append(_info(base, name, entry, commit))
    return PackListing(packs=tuple(packs), invalid=tuple(invalid))


def update_pack(
    name: str,
    *,
    ref: str | None = None,
    yes: bool = False,
    expected_identity: str | None = None,
    root: Path | None = None,
) -> PackUpdateResult:
    """Activate a new pinned revision of ``name`` only with explicit approval.

    Without approval ``ConsentRequired`` carries the change review and nothing changes. Older
    registered versions stay in the cache.
    """
    base = state_root(root)
    entry = load_state(base).packs.get(name)
    if entry is None:
        raise PackError("pack is not installed")
    start = entry.active
    with _stage(entry.source, ref or entry.ref, base) as staged, locked(base):
        state = load_state(base)
        entry = state.packs.get(name)
        if entry is None or entry.active != start:
            raise PackError(f"pack '{name}' changed concurrently")
        if staged.name != name or staged.snap.source != entry.source:
            raise PackError("fetched pack does not match the installed pack")
        commit = staged.snap.commit
        pack = identity_of(name, entry, staged.version)
        if expected_identity is not None and expected_identity != pack.identity:
            raise PackError("pack identity differs from the reviewed version")
        if commit == entry.active:
            _publish(base, staged, entry)
            if ref is not None and ref != entry.ref:
                updated = entry.model_copy(update={"ref": ref})
                save_state(base, State(packs={**state.packs, name: updated}))
                entry = updated
            return PackUpdateResult(
                current=_info(base, name, entry, commit), previous_commit=commit, changed=False
            )
        previous = entry.versions[entry.active]
        review = make_review(pack, staged.inspection.recipes, previous, staged.version.folders)
        if not yes:
            raise ConsentRequired(review)
        created = _publish(base, staged, entry)
        version = staged.version.model_copy(update={"consented": True})
        updated = entry.model_copy(
            update={
                "ref": ref or entry.ref,
                "active": commit,
                "versions": {**entry.versions, commit: version},
            }
        )
        new_state = State(packs={**state.packs, name: updated})
        try:
            save_state(base, new_state)
        except PackError as exc:
            if created and not isinstance(exc, PublishedStateError):
                remove_tree(cache_path(base, name, commit), expect=staged.filesystem_identity)
            raise
        return PackUpdateResult(
            current=_info(base, name, updated, commit),
            previous_commit=previous.commit,
            changed=True,
        )


def remove_pack(
    name: str,
    *,
    yes: bool = False,
    expected_identity: str | None = None,
    root: Path | None = None,
) -> PackRemoval:
    """Remove every cached version and consent of ``name``; sessions are never touched."""
    if not yes:
        raise PackError("removing a pack requires confirmation")
    base = state_root(root)
    with locked(base):
        state = load_state(base)
        entry = state.packs.get(name)
        if entry is None:
            raise PackError("pack is not installed")
        if (
            expected_identity is not None
            and expected_identity != entry.versions[entry.active].identity
        ):
            raise PackError("pack identity differs from the confirmed version")
        remaining = {n: e for n, e in state.packs.items() if n != name}
        save_state(base, State(packs=remaining))
        # Unregistered from here on: no rollback is possible or attempted, only honest reporting.
        failed = 0
        for commit in entry.versions:
            try:
                remove_tree(cache_path(base, name, commit))
            except PackError:
                failed += 1
        if failed:
            raise PackError(
                f"pack '{name}' was unregistered, but {failed} of {len(entry.versions)} cached "
                "versions could not be removed and remain on disk unregistered"
            )
        return PackRemoval(name=name, removed_versions=len(entry.versions))
