import json
from pathlib import Path
from unittest.mock import patch

import pytest

from patchground.report import submit_session
from patchground.sandbox import CommandResult, SandboxError
from patchground.sessions import SessionError, start_session
from patchground.sessions.practice import list_sessions, reveal_hint, run_session_command


def events(session: Path) -> list[dict]:
    return [
        json.loads(line) for line in (session / ".session/events.jsonl").read_text().splitlines()
    ]


def test_hints_are_frozen_ordered_and_exhaustion_does_not_log(authored, root, sandbox) -> None:
    manifest = authored / "challenge.yaml"
    manifest.write_text(manifest.read_text() + "\nhints: [first clue, second clue]\n")
    started = start_session(authored, root=root, sandbox=sandbox)
    manifest.write_text(manifest.read_text().replace("first clue", "source changed"))
    first = reveal_hint(started.session, root=root)
    assert (first.index, first.hint, first.remaining) == (1, "first clue", 1)
    assert reveal_hint(started.session, root=root).hint == "second clue"
    before = events(started.session)
    exhausted = reveal_hint(started.session, root=root)
    assert exhausted.exhausted and exhausted.hint is None and exhausted.remaining == 0
    assert exhausted.total == 2
    assert events(started.session) == before
    assert [event["data"] for event in before if event["type"] == "hint_revealed"] == [
        {"index": 1},
        {"index": 2},
    ]


def test_no_hints_is_success_without_event(authored, root, sandbox) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    before = events(started.session)
    result = reveal_hint(started.session, root=root)
    assert result.exhausted and result.total == 0
    assert events(started.session) == before


def test_session_listing_is_read_only_and_reports_invalid(authored, root, sandbox) -> None:
    assert list_sessions(root=root).sessions == ()
    first = start_session(authored, root=root, sandbox=sandbox)
    second = start_session(authored, root=root, sandbox=sandbox)
    bad = root / "broken/.session"
    bad.mkdir(parents=True)
    (bad / "session.json").write_text("invalid")
    (root / "unrelated").mkdir()
    (root / "unsafe").symlink_to(first.session, target_is_directory=True)
    with patch("subprocess.Popen", side_effect=AssertionError("must not execute")):
        listed = list_sessions(root=root)
    assert [item.session for item in listed.sessions] == [second.session, first.session]
    assert {item.session.name for item in listed.invalid} == {"broken", "unsafe"}


def test_command_uses_editable_copy_and_logs_no_arguments_or_output(
    authored, root, sandbox
) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    marker = "sensitive-argument-marker"
    output = "sensitive-output-marker"
    before_git = {
        str(p.relative_to(started.workspace)): p.read_bytes()
        for p in (started.workspace / ".git").rglob("*")
        if p.is_file()
    }

    class Commands:
        def run_command(self, image_id, layers, argv):
            assert image_id == "sha256:frozen"
            assert tuple(argv) == ("echo", marker, "--json")
            captured = layers[0]
            assert (captured / "code.py").exists()
            assert not (captured / "private.py").exists()
            assert not (captured / ".git").exists()
            (captured / "new-file").write_text("discarded")
            return CommandResult(exit_code=0, limit=None, output_tail=output)

    result = run_session_command(
        ["echo", marker, "--json"], started.session, root=root, sandbox=Commands()
    )
    assert result.output_tail == output
    assert not (started.workspace / "new-file").exists()
    log = (started.session / ".session/events.jsonl").read_text()
    assert marker not in log and output not in log
    assert events(started.session)[-1]["type"] == "command_run"
    after_git = {
        str(p.relative_to(started.workspace)): p.read_bytes()
        for p in (started.workspace / ".git").rglob("*")
        if p.is_file()
    }
    assert before_git == after_git


def test_closed_sessions_reject_hints_and_commands(authored, root, sandbox) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)
    submit_session(started.session, root=root, sandbox=sandbox)
    before = events(started.session)
    with pytest.raises(SessionError, match="submitted"):
        reveal_hint(started.session, root=root)
    with pytest.raises(SessionError, match="submitted"):
        run_session_command(["echo", "unused"], started.session, root=root)
    assert events(started.session) == before


def test_command_environment_errors_are_sanitized(authored, root, sandbox) -> None:
    started = start_session(authored, root=root, sandbox=sandbox)

    class Commands:
        def run_command(self, *args):
            raise SandboxError("private-engine-detail")

    with pytest.raises(SessionError, match="command unavailable") as error:
        run_session_command(
            ["echo", "private-argument"], started.session, root=root, sandbox=Commands()
        )
    assert "private-engine-detail" not in str(error.value)
    log = (started.session / ".session/events.jsonl").read_text()
    assert "private-engine-detail" not in log and "private-argument" not in log
