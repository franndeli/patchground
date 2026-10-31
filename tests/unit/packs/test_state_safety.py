import os

import pytest

from patchground.packs import store
from patchground.packs.models import PackError
from patchground.packs.registry import add_pack, list_packs, show_reference, update_pack


def fail_root_sync(root, monkeypatch):
    root.mkdir(parents=True, exist_ok=True)
    identity = root.stat()
    original = os.fsync

    def fail(fd):
        found = os.fstat(fd)
        if (found.st_dev, found.st_ino) == (identity.st_dev, identity.st_ino):
            raise OSError("simulated durability failure")
        original(fd)

    monkeypatch.setattr(store.os, "fsync", fail)


@pytest.mark.parametrize("updating", [False, True])
def test_published_registry_never_loses_its_cache_on_sync_failure(pack_repo, monkeypatch, updating):
    source, git = pack_repo
    root = store.state_root(None)
    if updating:
        old = add_pack(source)
        ticket = source / "pack-exercise/TICKET.md"
        ticket.write_text(ticket.read_text() + "\nRevision two.\n")
        git("add", "--all")
        git("commit", "-m", "Update pack")
    fail_root_sync(root, monkeypatch)
    with pytest.raises(store.PublishedStateError, match="was published"):
        if updating:
            update_pack("sample-pack", yes=True)
        else:
            add_pack(source)
    listing = list_packs()
    assert not listing.invalid
    active = next(info for info in listing.packs if info.active)
    assert active.pack.commit == git("rev-parse", "HEAD")
    assert active.path.is_dir()
    if updating:
        assert old.path.is_dir()


def test_unreadably_large_catalog_is_never_published(pack_repo, monkeypatch):
    source, _git = pack_repo
    monkeypatch.setattr(store, "MAX_STATE_BYTES", 1)
    with pytest.raises(PackError, match="size limit"):
        add_pack(source)
    root = store.state_root(None)
    assert not (root / "registry.json").exists()
    assert list((root / "packs").iterdir()) == []


def test_empty_directory_tampering_is_not_an_approved_input(pack_repo):
    source, _git = pack_repo
    info = add_pack(source)
    info.path.chmod(0o700)
    (info.path / "unreviewed-empty-directory").mkdir()
    assert list_packs().invalid
    with pytest.raises(PackError, match="integrity"):
        show_reference("sample-pack:pack-exercise")


def test_unchanged_update_still_checks_expected_identity(pack_repo):
    source, _git = pack_repo
    add_pack(source)
    before = (store.state_root(None) / "registry.json").read_bytes()
    with pytest.raises(PackError, match="identity differs"):
        update_pack("sample-pack", yes=True, expected_identity="0" * 64)
    assert (store.state_root(None) / "registry.json").read_bytes() == before
