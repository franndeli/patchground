import json
import os
import shlex

import pytest

from patchground.automation.workflow import validate_changes

pytestmark = pytest.mark.docker


def git_bytes(source):
    return {
        str(path.relative_to(source)): path.read_bytes()
        for path in (source / ".git").rglob("*")
        if path.is_file()
    }


def test_committed_validation_ignores_dirty_files_and_preserves_checkout(pack_repo, monkeypatch):
    source, git = pack_repo
    tools = source / "tools"
    tools.mkdir()
    marker = source / "untrusted-git-ran"
    fake_git = tools / "git"
    fake_git.write_text(f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\nexit 99\n")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    target = source / "pack-exercise/workspace/src/starter.py"
    target.write_text("DIRTY_CHECKOUT_CANARY = 'must never be imported or reported'\n")
    before = git_bytes(source)
    dirty = target.read_bytes()
    result = validate_changes(source, consent=True)
    assert result.exit_code == 0
    assert not marker.exists()
    data = result.to_dict()
    assert data["selected"] == ["pack-exercise"]
    assert "DIRTY_CHECKOUT_CANARY" not in json.dumps(data)
    assert str(source.parent) not in json.dumps(data)
    assert git_bytes(source) == before and target.read_bytes() == dirty
    assert not (source / "pack-exercise/verification.json").exists()
    skipped = validate_changes(source, base=git("rev-parse", "HEAD"), consent=False)
    assert skipped.exit_code == 0
    assert skipped.to_dict()["selected"] == []
    assert skipped.to_dict()["unchanged"] == ["pack-exercise"]


def test_failed_reference_is_reported_without_source_or_logs(pack_repo):
    source, git = pack_repo
    (source / "pack-exercise/solution/reference.patch").write_text(
        "REFERENCE_SENTINEL_DO_NOT_PRINT\n"
    )
    git("add", "--all")
    git("commit", "-m", "Break reference fixture")
    before = git_bytes(source)
    result = validate_changes(source, consent=True)
    assert result.exit_code == 1
    encoded = json.dumps(result.to_dict())
    assert "REFERENCE_SENTINEL_DO_NOT_PRINT" not in encoded
    assert str(source.parent) not in encoded
    assert git_bytes(source) == before
    assert not (source / "pack-exercise/verification.json").exists()
