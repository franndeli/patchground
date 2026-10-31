"""Atomic closure, immutable readback and unsafe artifact regression coverage."""

import json
import os
from pathlib import Path

import pytest

from patchground.sessions import (
    SessionError,
    check_session,
    check_submission,
    commit_submission,
    prepare_submission,
    read_submission,
    reset_session,
    session_status,
    start_session,
    store,
)

from .conftest import FakeSandbox


def test_frozen_closure(authored: Path, root: Path, sandbox: FakeSandbox) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    work = started.workspace
    git_before = {
        p.relative_to(work): p.read_bytes() for p in (work / ".git").rglob("*") if p.is_file()
    }
    (work / "ignored.txt").write_text("ordinary ignored file")
    (work / ".gitignore").write_text("ignored.txt\n")
    (work / ".env").write_text("synthetic private fixture")
    with prepare_submission(started.session, root=root) as snapshot:
        assert snapshot.saved_report is None
        assert (snapshot.final / "ignored.txt").exists()
        assert not (snapshot.final / ".env").exists()
        assert not (snapshot.final / ".git").exists()
        (work / "code.py").write_text("edited after freeze")
        assert (snapshot.final / "code.py").read_text() == "value = 0\n"
        for operation in (check_session, reset_session):
            with pytest.raises(SessionError, match="busy"):
                operation(started.session, root=root)
        result = check_submission(snapshot, sandbox=sandbox)
        commit_submission(snapshot, {"version": 1}, "# Saved\n", result)
    assert read_submission(started.session, root=root) == {"version": 1}
    status = session_status(started.session, root=root)
    assert status.state == "submitted"
    assert status.submitted_at == snapshot.requested_at
    assert status.last_check == result
    assert not any(e.type == "check_run" for e in store.load(started.session)[2])
    for operation in (check_session, reset_session):
        with pytest.raises(SessionError, match="already submitted"):
            operation(started.session, root=root)
    with prepare_submission(started.session, root=root) as repeated:
        assert repeated.saved_report == {"version": 1}
        commit_submission(repeated, {"different": True}, "different", result)
    assert sandbox.runs == 1
    assert len([e for e in store.load(started.session)[2] if e.type == "submitted"]) == 1
    assert git_before == {
        p.relative_to(work): p.read_bytes() for p in (work / ".git").rglob("*") if p.is_file()
    }


def test_precommit_failure_stays_active(
    authored: Path, root: Path, sandbox: FakeSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    import patchground.sessions.submission as submission

    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        with monkeypatch.context() as patch:
            patch.setattr(
                submission.os, "rename", lambda *a, **kw: (_ for _ in ()).throw(OSError("fault"))
            )
            with pytest.raises(SessionError):
                commit_submission(snapshot, {}, "", result)
    assert session_status(started.session, root=root).state == "active"
    with pytest.raises(SessionError, match="not submitted"):
        read_submission(started.session, root=root)
    with prepare_submission(started.session, root=root) as snapshot:
        commit_submission(snapshot, {"retry": True}, "", result)
    assert read_submission(started.session, root=root) == {"retry": True}


@pytest.mark.parametrize("torn", [False, True])
def test_postcommit_audit_recovery(
    authored: Path, root: Path, sandbox: FakeSandbox, monkeypatch: pytest.MonkeyPatch, torn: bool
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    journal = started.session / ".session/events.jsonl"
    original = journal.read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        if torn:
            with journal.open("ab") as stream:
                stream.write(b'{"ts":')
        raise OSError("audit fault")

    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        with monkeypatch.context() as patch:
            patch.setattr(store, "append_bytes", fail)
            with pytest.raises(SessionError, match=r"may already be published.*retry submit"):
                commit_submission(snapshot, {"saved": True}, "", result)
    assert read_submission(started.session, root=root) == {"saved": True}
    assert session_status(started.session, root=root).state == "submitted"
    for _ in range(2):
        with prepare_submission(started.session, root=root) as snapshot:
            assert snapshot.saved_report == {"saved": True}
    assert journal.read_bytes().startswith(original)
    assert len([e for e in store.load(started.session)[2] if e.type == "submitted"]) == 1


@pytest.mark.parametrize("artifact", ["receipt.json", "report.json", "report.md", "final/code.py"])
@pytest.mark.parametrize("damage", ["hardlink", "symlink", "corrupt"])
def test_unsafe_bundle(
    authored: Path, root: Path, sandbox: FakeSandbox, artifact: str, damage: str
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        commit_submission(snapshot, {}, "", result)
    target = started.session / ".session/submission" / artifact
    if damage == "hardlink":
        os.link(target, target.with_name("linked"))
    elif damage == "symlink":
        target.unlink()
        target.symlink_to(started.workspace / "code.py")
    else:
        target.write_text(json.dumps({"corrupt": True}))
    with pytest.raises(SessionError):
        read_submission(started.session, root=root)


def test_complete_event_without_newline_is_preserved(
    authored: Path, root: Path, sandbox: FakeSandbox
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        commit_submission(snapshot, {}, "", result)
    journal = started.session / ".session/events.jsonl"
    committed = journal.read_bytes()
    journal.write_bytes(committed.rstrip(b"\n"))
    with prepare_submission(started.session, root=root) as snapshot:
        assert snapshot.saved_report == {}
    assert journal.read_bytes() == committed


def test_engine_failure_stays_active(authored: Path, root: Path, sandbox: FakeSandbox) -> None:
    from patchground.sandbox import SandboxError

    started = start_session(authored, root=root, sandbox=sandbox)
    sandbox.error = SandboxError("synthetic infrastructure fault")
    with (
        pytest.raises(SessionError),
        prepare_submission(started.session, root=root) as snapshot,
    ):
        check_submission(snapshot, sandbox=sandbox)
    assert session_status(started.session, root=root).state == "active"
    assert len(store.load(started.session)[2]) == 1


def test_failing_check_can_close(authored: Path, root: Path, sandbox: FakeSandbox) -> None:
    from patchground.sandbox import RunOutcome, RunResult, TestResult, TestStatus

    started = start_session(authored, root=root, sandbox=sandbox)
    sandbox.result = RunResult(
        RunOutcome.FAILED, (TestResult("case", "case", "suite", TestStatus.FAILED),), 1, None, "raw"
    )
    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        assert not result.passed
        commit_submission(snapshot, {"failed": True}, "", result)
    assert session_status(started.session, root=root).last_check == result


@pytest.mark.parametrize("tree_name", ["workspace", ".session/original", ".session/hidden"])
@pytest.mark.parametrize("damage", ["missing", "symlink", "unsafe-entry"])
def test_completed_ignores_obsolete_inputs(
    authored: Path, root: Path, sandbox: FakeSandbox, tree_name: str, damage: str
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        commit_submission(snapshot, {"saved": True}, "", result)
    target = started.session / tree_name
    if damage == "unsafe-entry":
        target.chmod(0o700)
        (target / "unsafe").symlink_to(started.session)
    else:
        target.rename(target.with_name(target.name + "-old"))
        if damage == "symlink":
            target.symlink_to(started.session)
    journal = started.session / ".session/events.jsonl"
    before = journal.read_bytes()
    assert read_submission(started.session, root=root) == {"saved": True}
    assert session_status(started.session, root=root).state == "submitted"
    with prepare_submission(started.session, root=root) as repeated:
        assert repeated.saved_report == {"saved": True}
        commit_submission(repeated, {"replacement": True}, "replacement", result)
    assert journal.read_bytes() == before
    assert sandbox.runs == 1
    for operation in (check_session, reset_session):
        with pytest.raises(SessionError, match="already submitted"):
            operation(started.session, root=root)


@pytest.mark.parametrize("tree_name", ["workspace", ".session/original", ".session/hidden"])
def test_active_still_requires_safe_inputs(
    authored: Path, root: Path, sandbox: FakeSandbox, tree_name: str
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    target = started.session / tree_name
    target.rename(target.with_name(target.name + "-old"))
    target.symlink_to(started.session)
    with pytest.raises(SessionError):
        session_status(started.session, root=root)
    with pytest.raises(SessionError), prepare_submission(started.session, root=root):
        pass


@pytest.mark.parametrize(
    "damage", ["garbage", "other-event", "changed-history", "after-submission"]
)
def test_unproven_audit_corruption_is_rejected_without_writes(
    authored: Path, root: Path, sandbox: FakeSandbox, damage: str
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        commit_submission(snapshot, {}, "", result)
    journal = started.session / ".session/events.jsonl"
    raw = journal.read_bytes()
    prefix = raw[: raw.find(b"\n") + 1]
    if damage == "garbage":
        raw = prefix + b"not-json"
    elif damage == "other-event":
        raw = prefix + b'{"type":"check_run"'
    elif damage == "changed-history":
        raw = raw.replace(b"session_started", b"session_altered")
    else:
        raw += b'{"ts":'
    journal.write_bytes(raw)
    for operation in (read_submission, session_status):
        with pytest.raises(SessionError, match="corrupt"):
            operation(started.session, root=root)
    with (
        pytest.raises(SessionError, match="corrupt"),
        prepare_submission(started.session, root=root),
    ):
        pass
    assert journal.read_bytes() == raw


def test_postpublication_directory_sync_error_is_explicit(
    authored: Path, root: Path, sandbox: FakeSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    meta = started.session / ".session"
    identity = meta.stat().st_ino
    fsync = os.fsync

    def fail_after_publish(descriptor: int) -> None:
        if os.fstat(descriptor).st_ino == identity:
            raise OSError("directory sync fault")
        fsync(descriptor)

    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        with monkeypatch.context() as patch:
            patch.setattr(os, "fsync", fail_after_publish)
            with pytest.raises(SessionError, match=r"may already be published.*retry submit"):
                commit_submission(snapshot, {"saved": True}, "", result)
    assert read_submission(started.session, root=root) == {"saved": True}
    assert session_status(started.session, root=root).state == "submitted"
    with prepare_submission(started.session, root=root) as snapshot:
        assert snapshot.saved_report == {"saved": True}
    assert len([e for e in store.load(started.session)[2] if e.type == "submitted"]) == 1


def test_all_submission_append_prefixes_recover_without_rewriting(
    authored: Path, root: Path, sandbox: FakeSandbox
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    journal = started.session / ".session/events.jsonl"
    # Valid preexisting bytes must survive exactly, including noncanonical whitespace/newlines.
    journal.write_bytes(journal.read_bytes().replace(b"\n", b"\r\n"))
    baseline = journal.read_bytes()
    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        commit_submission(snapshot, {}, "", result)
    committed = journal.read_bytes()
    for length in range(len(baseline), len(committed) + 1):
        torn = committed[:length]
        journal.write_bytes(torn)
        assert read_submission(started.session, root=root) == {}
        assert journal.read_bytes() == torn  # Read-only callers never reconcile.
        with prepare_submission(started.session, root=root) as snapshot:
            assert snapshot.saved_report == {}
        assert journal.read_bytes() == committed
    store.append_event(started.session / ".session", "future_unknown", {"safe": True})
    with_extra = journal.read_bytes()
    with prepare_submission(started.session, root=root) as snapshot:
        assert snapshot.saved_report == {}
    assert journal.read_bytes() == with_extra


@pytest.mark.parametrize(
    "damage",
    [
        "version",
        "missing-version",
        "missing-proof",
        "null-proof",
        "missing-size",
        "missing-hash",
        "missing-event",
        "invalid-size",
        "invalid-hash",
        "invalid-event",
    ],
)
def test_malformed_or_unsupported_receipt_is_rejected_without_writes(
    authored: Path, root: Path, sandbox: FakeSandbox, damage: str
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        commit_submission(snapshot, {}, "", result)
    receipt = started.session / ".session/submission/receipt.json"
    data = json.loads(receipt.read_bytes())
    assert data["schema_version"] == 1
    if damage == "version":
        data["schema_version"] = 2
    elif damage == "missing-version":
        del data["schema_version"]
    elif damage == "missing-proof":
        del data["audit"]
    elif damage == "null-proof":
        data["audit"] = None
    elif damage.startswith("missing-"):
        field = {"size": "prefix_size", "hash": "prefix_sha256", "event": "event"}[
            damage.removeprefix("missing-")
        ]
        del data["audit"][field]
    elif damage == "invalid-size":
        data["audit"]["prefix_size"] = -1
    elif damage == "invalid-hash":
        data["audit"]["prefix_sha256"] = "invalid"
    else:
        data["audit"]["event"] = "not-json"
    receipt.write_text(json.dumps(data))
    journal = started.session / ".session/events.jsonl"
    before = journal.read_bytes()
    damaged_receipt = receipt.read_bytes()
    for operation in (read_submission, session_status):
        with pytest.raises(SessionError, match="corrupt"):
            operation(started.session, root=root)
    with (
        pytest.raises(SessionError, match="corrupt"),
        prepare_submission(started.session, root=root),
    ):
        pass
    assert journal.read_bytes() == before
    assert receipt.read_bytes() == damaged_receipt


def test_existing_schema_one_active_record_is_unchanged_on_submission(
    authored: Path, root: Path, sandbox: FakeSandbox
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    record = started.session / ".session/session.json"
    original = record.read_bytes()
    assert json.loads(original)["schema_version"] == 1
    assert session_status(started.session, root=root).state == "active"
    check_session(started.session, root=root, sandbox=sandbox)
    with prepare_submission(started.session, root=root) as snapshot:
        result = check_submission(snapshot, sandbox=sandbox)
        commit_submission(snapshot, {}, "", result)
    assert session_status(started.session, root=root).state == "submitted"
    assert record.read_bytes() == original
