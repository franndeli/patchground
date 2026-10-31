import os
from pathlib import Path

import pytest

from patchground.authoring import create_challenge
from patchground.report import submit_session
from patchground.sessions import check_session, start_session
from patchground.sessions.history import history_for_session
from patchground.sessions.practice import reveal_hint, run_session_command

pytestmark = pytest.mark.docker


def test_practice_tools_keep_hidden_inputs_and_user_git_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("PATCHGROUND_TEST_KEY", "fake-not-a-real-key")
    created = create_challenge("practice-tools")
    manifest = tmp_path / created.path / "challenge.yaml"
    manifest.write_text(manifest.read_text() + "\nhints: [A useful clue]\n")
    root = tmp_path / "sessions"
    started = start_session(tmp_path / created.path, root=root)
    git = started.workspace / ".git"
    before = {str(p.relative_to(git)): p.read_bytes() for p in git.rglob("*") if p.is_file()}
    assert reveal_hint(started.session, root=root).hint == "A useful clue"
    script = (
        "import os; from pathlib import Path; "
        "assert not Path('tests/test_starter_hidden.py').exists(); "
        "assert not Path('.git').exists(); "
        "assert not os.getenv('PATCHGROUND_TEST_KEY'); "
        "Path('generated.txt').write_text('discarded'); "
        "print('public-diagnostic-marker')"
    )
    command = run_session_command(["python", "-c", script], started.session, root=root)
    assert command.exit_code == 0
    assert "public-diagnostic-marker" in command.output_tail
    assert not (started.workspace / "generated.txt").exists()
    check = check_session(started.session, root=root)
    assert not check.passed
    assert check.history is not None and check.history.state == "recorded"
    history = history_for_session(started.session, root=root)
    assert history.availability == "available"
    assert [item.kind for item in history.snapshots] == ["initial", "check"]
    report = submit_session(started.session, root=root)
    assert report.effort.hints_revealed == 1
    assert report.effort.practice_checks == 1
    assert history_for_session(started.session, root=root) == history
    log = (started.session / ".session/events.jsonl").read_text()
    assert script not in log and "public-diagnostic-marker" not in log
    after = {str(p.relative_to(git)): p.read_bytes() for p in git.rglob("*") if p.is_file()}
    assert before == after
