import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from patchground.report.models import CheckEvidence
from patchground.report.workflow import saved_report, submit_session
from patchground.sandbox import RunOutcome, RunResult, TestResult, TestStatus
from patchground.sessions import SessionError, check_session, session_status


def git_bytes(session: Path) -> dict[str, bytes]:
    root = session / "workspace/.git"
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def test_report_is_frozen_and_no_raw_logs(session: Path, sandbox) -> None:
    before = git_bytes(session)
    report = submit_session(session, sandbox=sandbox)
    assert report.checks.passed
    assert report.regression.status == "not_verified"
    assert report.effort.practice_checks == 0
    assert sandbox.runs == 1
    assert git_bytes(session) == before
    (session / "workspace/src/starter.py").write_text("subsequent unrelated edit\n")
    sandbox.error = AssertionError("must not run again")
    assert submit_session(session, sandbox=sandbox) == report
    assert saved_report(session) == report
    assert "PRIVATE-RAW-LOG" not in report.model_dump_json()
    assert session_status(session).state == "submitted"
    with pytest.raises(SessionError, match="submitted"):
        check_session(session, sandbox=sandbox)
    markdown = (session / ".session/submission/report.md").read_text()
    assert "No overall score" in markdown
    assert "PRIVATE-RAW-LOG" not in markdown


def test_report_survives_removed_workspace(session: Path, sandbox) -> None:
    report = submit_session(session, sandbox=sandbox)
    shutil.rmtree(session / "workspace")
    assert saved_report(session) == report
    assert submit_session(session, sandbox=sandbox) == report


def test_saved_snapshot_permission_changes_are_detected(session: Path, sandbox) -> None:
    submit_session(session, sandbox=sandbox)
    (session / ".session/submission/final/src/starter.py").chmod(0o700)
    with pytest.raises(SessionError, match="submission"):
        saved_report(session)


def test_active_session_has_no_report(session: Path) -> None:
    with pytest.raises(SessionError, match="not submitted"):
        saved_report(session)


def test_failed_checks_still_finalize(session: Path, sandbox) -> None:
    sandbox.result = RunResult(
        RunOutcome.FAILED,
        (TestResult("fixture::case", "case", "fixture", TestStatus.FAILED),),
        1,
        None,
        "",
    )
    report = submit_session(session, sandbox=sandbox)
    assert not report.checks.passed
    assert saved_report(session) == report
    assert session_status(session).state == "submitted"


def test_prior_checks_counted_separately(session: Path, sandbox) -> None:
    check_session(session, sandbox=sandbox)
    report = submit_session(session, sandbox=sandbox)
    assert report.effort.practice_checks == 1
    assert sandbox.runs == 2


def test_report_roundtrip_and_derived_check_consistency(session: Path, sandbox) -> None:
    report = submit_session(session, sandbox=sandbox)
    assert type(report).model_validate_json(report.model_dump_json()) == report
    checks = json.loads(report.checks.model_dump_json())
    checks["counts"]["passed"] = 100
    with pytest.raises(ValidationError, match="inconsistent"):
        CheckEvidence.model_validate(checks)
