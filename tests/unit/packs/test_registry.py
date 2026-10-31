"""Installed packs: identity, consent, atomic catalog, retention, removal and tamper resistance.

Transport is replaced by a fake ``fetch_pack`` over a mutable directory; Git itself is covered by
the transport tests. Everything else (capture, hashing, cache, catalog, locks) is real.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from patchground.packs import registry, store
from patchground.packs.discovery import DiscoveryFilters
from patchground.packs.models import ConsentRequired, PackError, SourceSnapshot
from patchground.packs.registry import (
    add_pack,
    discover_installed,
    list_packs,
    prepare_execution,
    remove_pack,
    resolve_challenge,
    update_pack,
)

HIDDEN = "SYNTHETIC-HIDDEN-MARKER"
REFERENCE = "SYNTHETIC-REFERENCE-MARKER"


def make_challenge(parent: Path, name: str, *, dockerfile: str = "FROM scratch\n") -> None:
    path = parent / name
    for folder in ("workspace", "checks/visible", "checks/hidden", "environment", "solution"):
        (path / folder).mkdir(parents=True, exist_ok=True)
    (path / "workspace/code.py").write_text("value = 0\n")
    (path / "checks/visible/test_visible.py").write_text("# visible\n")
    (path / "checks/hidden/test_hidden.py").write_text(f"# {HIDDEN}\n")
    (path / "solution/reference.patch").write_text(REFERENCE)
    (path / "environment/Dockerfile").write_text(dockerfile)
    (path / "TICKET.md").write_text(f"Fix {name}\n")
    (path / "challenge.yaml").write_text(f"""spec_version: "0.1"
id: {name}
version: 1.0.0
title: Title of {name}
type: debug
summary: Summary of {name}
languages: [python]
tags: [caching]
difficulty: beginner
timebox_minutes: 20
ai_policy: allowed
environment:
  dockerfile: environment/Dockerfile
  services: [redis]
  test_command: pytest -q {name}
checks:
  visible: checks/visible
  hidden: checks/hidden
solution: solution/reference.patch
author: {{name: Fixture}}
""")


def make_pack(
    folder: Path,
    name: str = "demo",
    version: str = "1.0.0",
    challenges: tuple[str, ...] = ("alpha",),
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    listed = ", ".join(challenges)
    (folder / "pack.yaml").write_text(
        f'spec_version: "0.1"\nname: {name}\nversion: {version}\n'
        f"description: Demo pack\nchallenges: [{listed}]\n"
    )
    for challenge in challenges:
        make_challenge(folder, challenge)


class Remote:
    """A mutable fake Git remote: ``tree`` is the committed content at ``commit``."""

    def __init__(self, tree: Path, source: str) -> None:
        self.tree = tree
        self.source = source
        self.commit = self.bump("initial")

    def bump(self, label: str) -> str:
        self.commit = hashlib.sha1(label.encode(), usedforsecurity=False).hexdigest()
        return self.commit


@pytest.fixture
def state(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Remote:
    tree = tmp_path / "remote"
    make_pack(tree)
    fake = Remote(tree, str(tmp_path / "origin"))
    remotes = {fake.source: fake}
    monkeypatch.setattr(registry, "fetch_pack", _fetcher(remotes))
    fake.all = remotes  # type: ignore[attr-defined]
    return fake


def _fetcher(remotes: dict[str, Remote]):
    @contextmanager
    def fetch(source: str | Path, ref: str = "HEAD") -> Iterator[SourceSnapshot]:
        found = remotes.get(str(source))
        if found is None:
            raise PackError("source unavailable")
        yield SourceSnapshot(
            path=found.tree, source=found.source, source_kind="local", commit=found.commit
        )

    return fetch


def add_second(tmp_path: Path, remote: Remote, **kwargs: object) -> Remote:
    tree = tmp_path / f"remote-{len(remote.all)}"  # type: ignore[attr-defined]
    make_pack(tree, **kwargs)  # type: ignore[arg-type]
    other = Remote(tree, str(tmp_path / f"origin-{len(remote.all)}"))  # type: ignore[attr-defined]
    other.bump(other.source)
    remote.all[other.source] = other  # type: ignore[attr-defined]
    return other


def tree_snapshot(path: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(path)): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()
    }


# ---- install ------------------------------------------------------------------------------


def test_add_installs_sealed_pinned_unofficial_pack(remote: Remote, state: Path) -> None:
    info = add_pack(remote.source, root=state)
    assert info.pack.name == "demo"
    assert info.pack.commit == remote.commit
    assert info.pack.trust == "unofficial"
    assert info.consented is False and info.active is True
    assert info.path == state.resolve() / "packs" / f"demo@{remote.commit}"
    assert (info.path / "alpha/challenge.yaml").is_file()
    assert not os.access(info.path / "pack.yaml", os.W_OK)
    assert stat.S_IMODE(info.path.stat().st_mode) == 0o555
    assert list_packs(root=state).packs == (info,)


def test_add_is_idempotent_and_keeps_consent(remote: Remote, state: Path) -> None:
    first = add_pack(remote.source, root=state)
    with prepare_execution("demo:alpha", yes=True, root=state):
        pass
    again = add_pack(remote.source, root=state)
    assert again.pack == first.pack
    assert again.consented is True
    assert len(list_packs(root=state).packs) == 1


def test_add_refuses_other_revision_and_other_source(
    remote: Remote, state: Path, tmp_path: Path
) -> None:
    add_pack(remote.source, root=state)
    remote.bump("second")
    with pytest.raises(PackError, match="use pack update"):
        add_pack(remote.source, root=state)
    clash = add_second(tmp_path, remote)  # same pack name, different origin
    with pytest.raises(PackError, match="another source"):
        add_pack(clash.source, root=state)
    assert len(list_packs(root=state).packs) == 1


def test_read_only_operations_never_initialize_state(state: Path) -> None:
    assert list_packs(root=state).packs == ()
    assert discover_installed(root=state).challenges == ()
    assert resolve_challenge("not-installed", root=state).pack is None
    with pytest.raises(PackError):
        update_pack("demo", root=state)
    assert not state.exists()


@pytest.mark.parametrize("breakage", ["manifest", "challenge", "symlink", "id", "oversize"])
def test_invalid_or_unsafe_content_never_installs(
    remote: Remote, state: Path, breakage: str
) -> None:
    add_pack(remote.source, root=state)
    before = (state / "registry.json").read_bytes()
    remote.bump(breakage)
    if breakage == "manifest":
        (remote.tree / "pack.yaml").write_text("name: [broken\n")
    elif breakage == "challenge":
        (remote.tree / "alpha/challenge.yaml").write_text("id: alpha\n")
    elif breakage == "symlink":
        (remote.tree / "alpha/workspace/link").symlink_to("/etc/hosts")
    elif breakage == "id":
        text = (remote.tree / "alpha/challenge.yaml").read_text()
        (remote.tree / "alpha/challenge.yaml").write_text(text.replace("id: alpha", "id: other"))
    else:
        (remote.tree / "alpha/environment/Dockerfile").write_text("# x\n" * 40_000)
    with pytest.raises(PackError) as caught:
        update_pack("demo", yes=True, root=state)
    assert "/etc/hosts" not in str(caught.value)
    assert (state / "registry.json").read_bytes() == before
    assert not [p for p in (state / "packs").iterdir() if p.name.startswith(".stage-")]
    assert len(list_packs(root=state).packs) == 1


def test_manifest_error_names_file_and_line(remote: Remote, state: Path) -> None:
    (remote.tree / "alpha/challenge.yaml").write_text("id: alpha\n")
    with pytest.raises(PackError, match=r"alpha/challenge\.yaml:\d+"):
        add_pack(remote.source, root=state)
    assert not (state / "registry.json").exists()


# ---- resolution ---------------------------------------------------------------------------


def test_resolution_by_id_qualified_and_ambiguity(
    remote: Remote, state: Path, tmp_path: Path
) -> None:
    info = add_pack(remote.source, root=state)
    assert resolve_challenge("alpha", root=state).path == info.path / "alpha"
    assert resolve_challenge("demo:alpha", root=state).pack == info.pack
    other = add_second(tmp_path, remote, name="rival")
    add_pack(other.source, root=state)
    with pytest.raises(PackError, match=r"demo:alpha, rival:alpha"):
        resolve_challenge("alpha", root=state)
    assert resolve_challenge("rival:alpha", root=state).pack.name == "rival"  # type: ignore[union-attr]
    with pytest.raises(PackError, match="not installed"):
        resolve_challenge("ghost:alpha", root=state)


def test_local_paths_are_unchanged_and_ids_fall_back_to_paths(
    remote: Remote, state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_pack(remote.source, root=state)
    local = tmp_path / "mine"
    make_challenge(tmp_path, "mine")
    assert resolve_challenge(local, root=state).pack is None
    assert resolve_challenge(Path("./missing"), root=state).path == Path("./missing")
    monkeypatch.chdir(tmp_path)
    assert resolve_challenge("mine", root=state).path == Path("mine")
    with prepare_execution(local, root=state) as prepared:
        assert prepared.path == prepared.source_path == local
        assert prepared.pack is None and prepared.input_roots == ()
    with pytest.raises(PackError), prepare_execution(local, expected_identity="0" * 64, root=state):
        pass


def test_managed_paths_keep_pack_trust_without_bypass(
    remote: Remote, state: Path, tmp_path: Path
) -> None:
    info = add_pack(remote.source, root=state)
    managed = info.path / "alpha"
    assert resolve_challenge(managed, root=state).pack == info.pack
    for reference in (managed, str(managed)):
        with pytest.raises(ConsentRequired), prepare_execution(reference, root=state):
            pytest.fail("must not execute")
    link = tmp_path / "innocent"
    link.symlink_to(managed)
    with pytest.raises(ConsentRequired), prepare_execution(link, root=state):
        pytest.fail("symlink must not bypass consent")
    with pytest.raises(ConsentRequired), prepare_execution(managed / ".." / "alpha", root=state):
        pytest.fail("dotdot must not bypass consent")
    for bad in (info.path, info.path / "alpha/workspace", state / "packs" / ("demo@" + "0" * 40)):
        with pytest.raises(PackError), prepare_execution(bad, root=state):
            pytest.fail("not a challenge")


def test_unregistered_or_removed_cache_entries_have_no_path_fallback(
    remote: Remote, state: Path
) -> None:
    info = add_pack(remote.source, root=state)
    ghost = state.resolve() / "packs" / ("ghost@" + "1" * 40) / "alpha"
    ghost.mkdir(parents=True)
    with pytest.raises(PackError), prepare_execution(ghost, root=state):
        pytest.fail("unregistered cache path")
    store.remove_tree(info.path)
    with pytest.raises(PackError, match="missing"), prepare_execution("demo:alpha", root=state):
        pytest.fail("removed cache")
    with pytest.raises(PackError), prepare_execution(info.path / "alpha", root=state):
        pytest.fail("removed cache by path")


def test_discover_installed_filters_and_qualifies(remote: Remote, state: Path) -> None:
    info = add_pack(remote.source, root=state)
    found = discover_installed(root=state)
    [summary] = found.challenges
    assert summary.reference == "demo:alpha"
    assert summary.pack == info.pack
    assert summary.path == str(info.path / "alpha")
    assert discover_installed(DiscoveryFilters(tag="CACHING"), root=state).challenges
    assert not discover_installed(DiscoveryFilters(lang="go"), root=state).challenges
    store.remove_tree(info.path)
    gone = discover_installed(root=state)
    assert gone.challenges == () and gone.invalid


# ---- consent and preparation --------------------------------------------------------------


def test_no_consent_returns_full_safe_review_before_execution(
    remote: Remote, state: Path, tmp_path: Path
) -> None:
    make_challenge(remote.tree, "beta", dockerfile="FROM python:3.12\nRUN make\n")
    (remote.tree / "pack.yaml").write_text(
        'spec_version: "0.1"\nname: demo\nversion: 1.0.0\ndescription: d\n'
        "challenges: [alpha, beta]\n"
    )
    info = add_pack(remote.source, root=state)
    entered = False
    with pytest.raises(ConsentRequired) as caught, prepare_execution("alpha", root=state):
        entered = True
    assert not entered
    review = caught.value.review
    assert review.pack == info.pack
    assert [r.challenge_id for r in review.recipes] == ["alpha", "beta"]
    beta = review.recipes[1]
    assert beta.dockerfile == "FROM python:3.12\nRUN make\n"
    assert beta.services == ("redis",) and beta.command == "pytest -q beta"
    assert HIDDEN not in review.model_dump_json() and REFERENCE not in review.model_dump_json()
    assert not list_packs(root=state).packs[0].consented
    assert not [p for p in Path(tmp_path).glob("patchground-pack-*")]


def test_yes_records_consent_and_serves_a_verified_private_copy(
    remote: Remote, state: Path
) -> None:
    info = add_pack(remote.source, root=state)
    with prepare_execution("demo:alpha", yes=True, root=state) as prepared:
        copy_root = prepared.path.parent
        assert prepared.source_path == info.path / "alpha"
        assert prepared.path != prepared.source_path
        assert prepared.pack == info.pack
        assert copy_root in prepared.input_roots and info.path in prepared.input_roots
        assert (prepared.path / "checks/hidden/test_hidden.py").is_file()
        assert os.access(prepared.path / "workspace/code.py", os.W_OK)
        (prepared.path / "workspace/code.py").write_text("mutated\n")
    assert not copy_root.exists()
    assert (info.path / "alpha/workspace/code.py").read_text() == "value = 0\n"
    assert list_packs(root=state).packs[0].consented
    with prepare_execution("alpha", root=state):  # persisted consent, no flag needed
        pass


def test_expected_identity_binds_the_reviewed_version(remote: Remote, state: Path) -> None:
    info = add_pack(remote.source, root=state)
    with (
        pytest.raises(PackError, match="differs"),
        prepare_execution("alpha", yes=True, expected_identity="f" * 64, root=state),
    ):
        pass
    assert not list_packs(root=state).packs[0].consented
    with prepare_execution("alpha", yes=True, expected_identity=info.pack.identity, root=state):
        pass


def test_cache_tampering_is_detected_even_after_consent_review(remote: Remote, state: Path) -> None:
    info = add_pack(remote.source, root=state)
    with pytest.raises(ConsentRequired) as caught, prepare_execution("alpha", root=state):
        pass
    identity = caught.value.review.pack.identity
    target = info.path / "alpha/environment/Dockerfile"
    info.path.chmod(0o755)
    (info.path / "alpha/environment").chmod(0o755)
    target.chmod(0o644)
    target.write_text("FROM evil\n")
    with (
        pytest.raises(PackError, match="integrity"),
        prepare_execution("alpha", yes=True, expected_identity=identity, root=state),
    ):
        pass
    listing = list_packs(root=state)
    assert listing.packs == () and "integrity" in listing.invalid[0].reason
    [recorded] = json.loads((state / "registry.json").read_text())["packs"]["demo"][
        "versions"
    ].values()
    assert recorded["consented"] is False


def test_swapped_cache_with_links_is_rejected(remote: Remote, state: Path, tmp_path: Path) -> None:
    info = add_pack(remote.source, root=state)
    decoy = tmp_path / "decoy"
    shutil.copytree(info.path, decoy)
    store.remove_tree(info.path)
    info.path.symlink_to(decoy)
    with pytest.raises(PackError), prepare_execution("demo:alpha", yes=True, root=state):
        pytest.fail("symlinked pack directory must be refused")
    store.remove_tree(info.path)
    shutil.copytree(decoy, info.path)
    (info.path / "alpha/workspace").chmod(0o755)
    (info.path / "alpha/workspace/link").symlink_to("/etc/hosts")
    with pytest.raises(PackError), prepare_execution("demo:alpha", yes=True, root=state):
        pytest.fail("planted symlink must be refused")


# ---- catalog integrity --------------------------------------------------------------------


def _rewrite(state: Path, mutate) -> None:
    path = state / "registry.json"
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["packs"]["demo"].update(source="https://user:pw@example.com/x.git"),
        lambda d: d["packs"]["demo"].update(source_kind="https"),
        lambda d: d["packs"]["demo"].update(active="2" * 40),
        lambda d: d["packs"]["demo"].update(ref="a\nb"),
        lambda d: next(iter(d["packs"]["demo"]["versions"].values())).update(digest="3" * 64),
        lambda d: next(iter(d["packs"]["demo"]["versions"].values())).update(identity="4" * 64),
        lambda d: d["packs"].update({"../escape": d["packs"]["demo"]}),
        lambda d: d.update(extra=True),
    ],
)
def test_corrupt_or_unsafe_catalog_fails_closed_without_repair(
    remote: Remote, state: Path, mutate
) -> None:
    add_pack(remote.source, root=state)
    _rewrite(state, mutate)
    broken = (state / "registry.json").read_bytes()
    for call in (
        lambda: list_packs(root=state),
        lambda: discover_installed(root=state),
        lambda: resolve_challenge("alpha", root=state),
        lambda: add_pack(remote.source, root=state),
        lambda: update_pack("demo", yes=True, root=state),
        lambda: remove_pack("demo", yes=True, root=state),
    ):
        with pytest.raises(PackError, match="registry"):
            call()
    assert (state / "registry.json").read_bytes() == broken


def test_non_json_oversize_and_symlinked_catalogs_fail(remote: Remote, state: Path) -> None:
    add_pack(remote.source, root=state)
    path = state / "registry.json"
    good = path.read_bytes()
    for bad in (b"{", b"[]", b" " * (store.MAX_STATE_BYTES + 1)):
        path.write_bytes(bad)
        with pytest.raises(PackError, match="registry"):
            list_packs(root=state)
    path.unlink()
    elsewhere = state / "elsewhere.json"
    elsewhere.write_bytes(good)
    path.symlink_to(elsewhere)
    with pytest.raises(PackError, match="registry"):
        list_packs(root=state)


# ---- update -------------------------------------------------------------------------------


def test_update_requires_explicit_approval_and_previews_changes(
    remote: Remote, state: Path
) -> None:
    old = add_pack(remote.source, root=state)
    make_challenge(remote.tree, "beta")
    (remote.tree / "alpha/environment/Dockerfile").write_text("FROM python:3.13\n")
    (remote.tree / "pack.yaml").write_text(
        'spec_version: "0.1"\nname: demo\nversion: 1.1.0\ndescription: d\n'
        "challenges: [alpha, beta]\n"
    )
    remote.bump("v2")
    before = (state / "registry.json").read_bytes()
    with pytest.raises(ConsentRequired) as caught:
        update_pack("demo", root=state)
    review = caught.value.review
    assert review.previous_commit == old.pack.commit
    assert (review.added, review.removed, review.changed) == (("beta",), (), ("alpha",))
    assert review.recipes[0].dockerfile == "FROM python:3.13\n"
    assert (state / "registry.json").read_bytes() == before
    assert list_packs(root=state).packs[0].pack == old.pack
    with pytest.raises(PackError, match="differs"):
        update_pack("demo", yes=True, expected_identity="e" * 64, root=state)
    assert list_packs(root=state).packs[0].pack == old.pack

    result = update_pack("demo", yes=True, expected_identity=review.pack.identity, root=state)
    assert result.changed and result.previous_commit == old.pack.commit
    assert result.current.pack == review.pack and result.current.consented
    listing = list_packs(root=state).packs
    assert [(p.pack.commit, p.active) for p in listing] == [
        (old.pack.commit, False),
        (remote.commit, True),
    ]
    assert (old.path / "alpha/environment/Dockerfile").read_text() == "FROM scratch\n"
    assert resolve_challenge("alpha", root=state).path == result.current.path / "alpha"
    # the retained version keeps its own consent state and is still reachable by path
    with pytest.raises(ConsentRequired), prepare_execution(old.path / "alpha", root=state):
        pytest.fail("old version was never approved")
    again = update_pack("demo", root=state)
    assert not again.changed


def test_update_rejects_renamed_pack_and_follows_recorded_ref(remote: Remote, state: Path) -> None:
    add_pack(remote.source, ref="main", root=state)
    seen: list[str] = []
    real = registry.fetch_pack

    @contextmanager
    def spy(source, ref="HEAD"):
        seen.append(ref)
        with real(source, ref) as snap:
            yield snap

    registry.fetch_pack = spy  # monkeypatch fixture restores the attribute
    try:
        update_pack("demo", root=state)
        update_pack("demo", ref="v2", root=state)
        update_pack("demo", root=state)
    finally:
        registry.fetch_pack = real
    assert seen == ["main", "v2", "v2"]
    (remote.tree / "pack.yaml").write_text(
        'spec_version: "0.1"\nname: renamed\nversion: 1.0.0\ndescription: d\nchallenges: [alpha]\n'
    )
    remote.bump("rename")
    with pytest.raises(PackError, match="does not match"):
        update_pack("demo", yes=True, root=state)
    assert list_packs(root=state).packs[0].pack.name == "demo"


def test_failed_catalog_write_rolls_back_update_and_add(
    remote: Remote, state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(root: Path, new: store.State) -> None:
        raise PackError("pack registry could not be written")

    monkeypatch.setattr(registry, "save_state", explode)
    with pytest.raises(PackError):
        add_pack(remote.source, root=state)
    assert not (state / "registry.json").exists()
    assert [p.name for p in (state / "packs").iterdir()] == []
    monkeypatch.undo()
    monkeypatch.setattr(registry, "fetch_pack", _fetcher({remote.source: remote}))
    old = add_pack(remote.source, root=state)
    before = (state / "registry.json").read_bytes()
    remote.bump("v2")
    monkeypatch.setattr(registry, "save_state", explode)
    with pytest.raises(PackError):
        update_pack("demo", yes=True, root=state)
    assert (state / "registry.json").read_bytes() == before
    assert [p.name for p in (state / "packs").iterdir()] == [f"demo@{old.pack.commit}"]
    assert list_packs(root=state).packs[0].active


def test_interrupted_atomic_replace_keeps_old_catalog(
    remote: Remote, state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_pack(remote.source, root=state)
    before = (state / "registry.json").read_bytes()
    remote.bump("v2")

    def crash(*args: object, **kwargs: object) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr(store.os, "replace", crash)
    with pytest.raises(PackError):
        update_pack("demo", yes=True, root=state)
    monkeypatch.undo()
    assert (state / "registry.json").read_bytes() == before
    assert not [p for p in state.iterdir() if p.name.endswith(".tmp")]


def test_unregistered_destination_is_never_deleted_or_swept(remote: Remote, state: Path) -> None:
    packs = state.resolve() / "packs"
    orphan = packs / f"demo@{remote.commit}"
    (orphan / "alpha").mkdir(parents=True)
    (orphan / "alpha/precious").write_text("planted")
    unrelated = packs / "notes.txt"
    unrelated.write_text("keep")
    stray = packs / ("other@" + "5" * 40)
    stray.mkdir()
    stage_named = packs / ".stage-user-data"
    stage_named.mkdir()
    old = time.time() - 10 * 86400
    os.utime(stage_named, (old, old))
    with pytest.raises(PackError, match="not replaced"):
        add_pack(remote.source, root=state)
    assert (orphan / "alpha/precious").read_text() == "planted"
    assert not (state / "registry.json").exists()
    shutil.rmtree(orphan)
    add_pack(remote.source, root=state)  # unrelated leftovers never blocked or swept
    assert unrelated.exists() and stray.exists() and stage_named.exists()


def test_identical_unregistered_destination_is_adopted_after_interrupted_add(
    remote: Remote, state: Path
) -> None:
    info = add_pack(remote.source, root=state)
    (state / "registry.json").unlink()  # crash between cache publish and catalog write
    again = add_pack(remote.source, root=state)
    assert again.pack == info.pack
    assert list_packs(root=state).packs[0].path == info.path
    assert not [p for p in (state / "packs").iterdir() if p.name.startswith(".stage-")]


def test_idempotent_add_verifies_actual_registered_cache_bytes(remote: Remote, state: Path) -> None:
    info = add_pack(remote.source, root=state)
    target = info.path / "alpha/environment/Dockerfile"
    (info.path / "alpha/environment").chmod(0o755)
    target.chmod(0o644)
    target.write_text("FROM evil\n")  # catalog digest still equals the incoming digest
    with pytest.raises(PackError, match="integrity"):
        add_pack(remote.source, root=state)
    assert target.read_text() == "FROM evil\n"


def test_stage_cleanup_leaves_a_replacement_at_the_staged_path(
    remote: Remote, state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    survivors: list[Path] = []
    real = registry.inspect_pack

    def swap(folder: Path):
        inspection = real(folder)
        store.remove_tree(folder)
        folder.mkdir()
        (folder / "theirs").write_text("not ours")
        survivors.append(folder)
        return inspection

    monkeypatch.setattr(registry, "inspect_pack", swap)
    with pytest.raises(PackError, match="changed before publication"):
        add_pack(remote.source, root=state)
    assert (survivors[0] / "theirs").read_text() == "not ours"  # cleanup skipped the replacement
    assert not (state / "registry.json").exists()
    assert not list((state / "packs").glob("demo@*"))


def test_held_stage_identity_cannot_be_recycled_by_a_replacement(tmp_path: Path) -> None:
    stage = tmp_path / ".stage-x"
    stage.mkdir()
    with store.hold_stage(stage) as identity:
        store.remove_tree(stage)
        stage.mkdir()  # filesystems may hand a freed inode back; a held one is never free
        (stage / "theirs").write_text("not ours")
        info = stage.lstat()
        assert (info.st_dev, info.st_ino) != identity
        store.remove_tree(stage, expect=identity)
    assert (stage / "theirs").read_text() == "not ours"


def test_remove_tree_preserves_a_root_swapped_between_stat_and_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / ".stage-x"
    target.mkdir()
    (target / "ours").write_text("ours")
    real_open = os.open
    swapped = False

    def swap_then_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and path == target.name and kwargs.get("dir_fd") is not None:
            swapped = True  # the vetted root is replaced after it was statted
            target.rename(tmp_path / "moved-original")
            target.mkdir()
            (target / "theirs").write_text("not ours")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_then_open)
    store.remove_tree(target)
    assert swapped
    assert (target / "theirs").read_text() == "not ours"
    assert (tmp_path / "moved-original/ours").read_text() == "ours"


# ---- removal ------------------------------------------------------------------------------


def test_remove_confirms_clears_versions_and_consent_but_not_sessions(
    remote: Remote, state: Path, tmp_path: Path
) -> None:
    add_pack(remote.source, root=state)
    remote.bump("v2")
    update_pack("demo", yes=True, root=state)
    session = state / "sessions" / "s1"
    session.mkdir(parents=True)
    (session / "frozen.txt").write_text("frozen copy")
    keep = state / "packs" / "notes.txt"
    keep.write_text("keep")
    active = list_packs(root=state).packs[-1].pack
    with pytest.raises(PackError, match="confirmation"):
        remove_pack("demo", root=state)
    with pytest.raises(PackError, match="differs"):
        remove_pack("demo", yes=True, expected_identity="9" * 64, root=state)
    with pytest.raises(PackError, match="not installed"):
        remove_pack("ghost", yes=True, root=state)
    removal = remove_pack("demo", yes=True, expected_identity=active.identity, root=state)
    assert removal.removed_versions == 2
    assert list_packs(root=state).packs == ()
    assert [p.name for p in (state / "packs").iterdir()] == ["notes.txt"]
    assert keep.read_text() == "keep" and (session / "frozen.txt").read_text() == "frozen copy"
    assert (remote.tree / "pack.yaml").is_file()
    with pytest.raises(ConsentRequired):
        add_pack(remote.source, root=state)
        with prepare_execution("alpha", root=state):
            pass


def test_prepared_copy_survives_removal_until_released(remote: Remote, state: Path) -> None:
    add_pack(remote.source, root=state)
    with prepare_execution("alpha", yes=True, root=state) as prepared:
        remove_pack("demo", yes=True, root=state)
        assert (prepared.path / "challenge.yaml").is_file()


# ---- concurrency --------------------------------------------------------------------------


def test_concurrent_adds_publish_every_pack_exactly_once(
    remote: Remote, state: Path, tmp_path: Path
) -> None:
    others = [add_second(tmp_path, remote, name=f"pack-{i}") for i in range(6)]
    sources = [remote.source, *(o.source for o in others), remote.source, others[0].source]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda s: add_pack(s, root=state), sources))
    names = sorted(p.pack.name for p in list_packs(root=state).packs)
    assert names == sorted(["demo", *(f"pack-{i}" for i in range(6))])
    assert len(list((state / "packs").iterdir())) == 7


def test_concurrent_updates_never_corrupt_the_catalog(remote: Remote, state: Path) -> None:
    add_pack(remote.source, root=state)
    remote.bump("v2")

    def attempt(_: int) -> str:
        try:
            update_pack("demo", yes=True, root=state)
        except PackError:
            return "refused"
        return "ok"

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, range(6)))
    assert "ok" in results
    listing = list_packs(root=state).packs
    assert sorted(p.active for p in listing) == [False, True]
    assert [p.pack.commit for p in listing if p.active] == [remote.commit]


# ---- follow-up regressions ----------------------------------------------------------------


def test_existing_local_folder_beats_bare_id_but_qualified_selects_installed(
    remote: Remote, state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    info = add_pack(remote.source, root=state)
    workdir = tmp_path / "work"
    make_challenge(workdir, "alpha")
    monkeypatch.chdir(workdir)
    assert resolve_challenge("alpha", root=state).pack is None
    assert resolve_challenge("alpha", root=state).path == Path("alpha")
    assert resolve_challenge("demo:alpha", root=state).pack == info.pack
    with prepare_execution("./alpha", root=state) as local:
        assert local.pack is None and local.path == Path("alpha")
    monkeypatch.chdir(tmp_path)  # no local folder: the bare id selects the installed pack
    assert resolve_challenge("alpha", root=state).pack == info.pack


def test_prepared_input_roots_include_the_original_local_source(
    remote: Remote, state: Path
) -> None:
    info = add_pack(remote.source, root=state)
    with prepare_execution("alpha", yes=True, root=state) as prepared:
        assert Path(remote.source) in prepared.input_roots
        assert info.path in prepared.input_roots and prepared.path.parent in prepared.input_roots


def test_aggregate_recipe_review_is_bounded_and_fails_instead_of_truncating(
    remote: Remote, state: Path
) -> None:
    names = tuple(f"big-{i}" for i in range(20))
    shutil.rmtree(remote.tree / "alpha")
    make_pack(remote.tree, challenges=names)
    for name in names:  # 60 000 B each: under the per-file cap, over 1 MiB together
        (remote.tree / name / "environment/Dockerfile").write_text("# x\n" * 15_000)
    with pytest.raises(PackError, match="too large to review"):
        add_pack(remote.source, root=state)
    assert not (state / "registry.json").exists()


def test_partial_removal_failure_is_reported_after_unregistration(
    remote: Remote, state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_pack(remote.source, root=state)
    remote.bump("v2")
    update_pack("demo", yes=True, root=state)
    real = registry.remove_tree
    monkeypatch.setattr(
        registry,
        "remove_tree",
        lambda path, **kw: (
            (_ for _ in ()).throw(PackError("busy"))
            if f"@{remote.commit}" in str(path)
            else real(path, **kw)
        ),
    )
    with pytest.raises(PackError, match=r"unregistered, but 1 of 2"):
        remove_pack("demo", yes=True, root=state)
    assert list_packs(root=state).packs == ()  # no fabricated rollback
    leftovers = [p.name for p in (state / "packs").iterdir()]
    assert leftovers == [f"demo@{remote.commit}"]


def test_managed_looking_paths_never_fall_back_to_local(remote: Remote, state: Path) -> None:
    base = state.resolve() / "packs"
    ghost = base / ("demo@" + "6" * 40) / "alpha"
    for reference in (ghost, str(ghost), base / "demo@x" / "alpha", base):
        assert not base.exists()
        with pytest.raises(PackError), prepare_execution(reference, root=state):
            pytest.fail("cache path with missing base must not be trusted as local")
        with pytest.raises(PackError):
            resolve_challenge(reference, root=state)
    info = add_pack(remote.source, root=state)
    (state / "registry.json").write_text("{")
    with (
        pytest.raises(PackError, match="registry"),
        prepare_execution(info.path / "alpha", root=state),
    ):
        pytest.fail("corrupt registry must not downgrade a managed path to local")
    local = state.parent / "elsewhere"
    local.mkdir()
    with prepare_execution(local, root=state) as prepared:  # truly local paths are unaffected
        assert prepared.pack is None


def test_show_reference_uses_verified_copy_without_consent(remote: Remote, state: Path) -> None:
    info = add_pack(remote.source, root=state)
    details = registry.show_reference("demo:alpha", root=state)
    assert details.valid and details.ticket == "Fix alpha\n"
    assert details.path == str(info.path / "alpha")
    assert details.challenge.path == str(info.path / "alpha")  # type: ignore[union-attr]
    assert HIDDEN not in details.model_dump_json()
    assert not list_packs(root=state).packs[0].consented  # showing grants nothing
    assert registry.show_reference(info.path / "alpha", root=state).path == details.path
    target = info.path / "alpha/TICKET.md"
    (info.path / "alpha").chmod(0o755)
    target.chmod(0o644)
    target.write_text("tampered\n")
    with pytest.raises(PackError, match="integrity"):
        registry.show_reference("demo:alpha", root=state)


def test_show_reference_leaves_local_paths_to_discovery(
    remote: Remote, state: Path, tmp_path: Path
) -> None:
    make_challenge(tmp_path, "mine")
    details = registry.show_reference(tmp_path / "mine", root=state)
    assert details.valid and details.path == str(tmp_path / "mine")
    assert not state.exists()


def test_read_only_listings_flag_tampered_cache(remote: Remote, state: Path) -> None:
    info = add_pack(remote.source, root=state)
    (info.path / "alpha/workspace").chmod(0o755)
    (info.path / "alpha/workspace/code.py").chmod(0o644)
    (info.path / "alpha/workspace/code.py").write_text("evil = 1\n")
    listing = list_packs(root=state)
    assert listing.packs == () and "integrity" in listing.invalid[0].reason
    found = discover_installed(root=state)
    assert found.challenges == () and "integrity" in found.invalid[0].issues[0]
