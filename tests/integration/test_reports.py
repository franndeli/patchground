"""Real Docker reports from captured input; reference solutions are never used to solve."""

from pathlib import Path
from unittest.mock import patch

import pytest

from patchground.authoring import create_challenge
from patchground.report.workflow import saved_report, submit_session
from patchground.sessions import SessionError, check_session, session_status, start_session

pytestmark = pytest.mark.docker


def _git_bytes(workspace: Path) -> dict[str, bytes]:
    git = workspace / ".git"
    return {
        str(path.relative_to(git)): path.read_bytes() for path in git.rglob("*") if path.is_file()
    }


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_verified_regression_and_immutable_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    monkeypatch.chdir(tmp_path)
    created = create_challenge("submission-example", language=language)
    root = tmp_path / "sessions"
    started = start_session(tmp_path / created.path, root=root)
    baseline = _git_bytes(started.workspace)
    if language == "python":
        code = started.workspace / "src/starter.py"
        code.write_text(code.read_text().replace("sum(items[:-1])", "sum(items)"))
        (started.workspace / "tests/test_regression.py").write_text(
            "from starter import total\n\ndef test_last_amount_is_included():\n"
            "    assert total([2, 3]) == 5\n"
        )
    else:
        code = started.workspace / "src/starter.ts"
        code.write_text(code.read_text().replace("items.slice(0, -1)", "items"))
        (started.workspace / "tests/regression.test.ts").write_text(
            'import {test, expect} from "vitest";\n'
            'import {total} from "../src/starter";\n'
            'test("last amount is included", () => { expect(total([2, 3])).toBe(5); });\n'
        )
    report = submit_session(started.session, root=root)
    assert report.checks.passed
    assert report.regression.status == "verified", report.regression.reason
    assert len(report.regression.verified_tests) == 1
    assert report.effort.practice_checks == 0
    assert _git_bytes(started.workspace) == baseline
    assert session_status(started.session, root=root).state == "submitted"
    with pytest.raises(SessionError, match="submitted"):
        check_session(started.workspace, root=root)
    code.write_text("a later edit is not the submitted solution\n")
    with patch("patchground.sandbox.run_check", side_effect=AssertionError("must not execute")):
        assert submit_session(started.session, root=root) == report
        assert saved_report(started.session, root=root) == report
    assert _git_bytes(started.workspace) == baseline


def test_failed_attempt_can_finalize_without_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    created = create_challenge("unfinished-example")
    root = tmp_path / "sessions"
    started = start_session(tmp_path / created.path, root=root, timer=False)
    report = submit_session(started.session, root=root)
    assert not report.checks.passed
    assert report.regression.status == "not_verified"
    assert report.effort.elapsed_seconds is None
    assert saved_report(started.session, root=root) == report
