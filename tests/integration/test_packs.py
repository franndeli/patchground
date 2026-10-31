from pathlib import Path

import pytest

from patchground.packs.models import ConsentRequired
from patchground.packs.registry import add_pack, remove_pack, update_pack
from patchground.sessions import check_session, start_session
from patchground.sessions.store import load
from patchground.verify import VerifyEnvironmentError, validate_challenge

pytestmark = pytest.mark.docker


def test_installed_validation_and_session_survive_update_and_removal(pack_repo) -> None:
    source, git = pack_repo
    installed = add_pack(source)
    cached = installed.path / "pack-exercise"
    with pytest.raises(ConsentRequired):
        validate_challenge(cached)
    report = validate_challenge("sample-pack:pack-exercise", yes=True)
    assert report.valid and report.verification_file is None
    assert not (cached / "verification.json").exists()
    started = start_session("sample-pack:pack-exercise")
    metadata = started.session / ".session"
    record, _manifest, _events = load(started.session)
    assert record.pack is not None and record.pack.commit == installed.pack.commit
    assert Path(record.source) == cached
    before = {
        str(path.relative_to(started.workspace)): path.read_bytes()
        for path in (started.workspace / ".git").rglob("*")
        if path.is_file()
    }
    assert not check_session(started.session).passed
    ticket = source / "pack-exercise/TICKET.md"
    ticket.write_text(ticket.read_text() + "\nNew upstream ticket.\n")
    git("add", "--all")
    git("commit", "-m", "Change upstream ticket")
    updated = update_pack("sample-pack", yes=True)
    assert updated.current.pack.commit != record.pack.commit
    assert "New upstream ticket" not in (metadata / "TICKET.md").read_text()
    removed = remove_pack("sample-pack", yes=True)
    assert removed.removed_versions == 2
    assert not check_session(started.session).passed
    with pytest.raises(VerifyEnvironmentError):
        validate_challenge(cached)
    after = {
        str(path.relative_to(started.workspace)): path.read_bytes()
        for path in (started.workspace / ".git").rglob("*")
        if path.is_file()
    }
    assert before == after
