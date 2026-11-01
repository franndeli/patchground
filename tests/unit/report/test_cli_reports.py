import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from patchground.cli.app import app
from patchground.sandbox import RunOutcome, RunResult, TestResult, TestStatus

runner = CliRunner()


def test_submit_and_read_json(session: Path, sandbox) -> None:
    with patch("patchground.sandbox.run_check", side_effect=sandbox.run_check):
        submitted = runner.invoke(app, ["submit", "--session", str(session), "--json"])
    assert submitted.exit_code == 0
    assert submitted.stderr == ""
    report = runner.invoke(app, ["report", "--session", str(session), "--json"])
    assert report.exit_code == 0
    assert json.loads(report.stdout) == json.loads(submitted.stdout)
    assert "PRIVATE-RAW-LOG" not in submitted.stdout


def test_failed_submit_exit_code_and_report_read_success(session: Path, sandbox) -> None:
    sandbox.result = RunResult(
        RunOutcome.FAILED,
        (TestResult("fixture::case", "case", "fixture", TestStatus.FAILED),),
        1,
        None,
        "",
    )
    with patch("patchground.sandbox.run_check", side_effect=sandbox.run_check):
        submitted = runner.invoke(app, ["submit", "--session", str(session), "--json"])
    assert submitted.exit_code == 1
    assert json.loads(submitted.stdout)["checks"]["passed"] is False
    assert runner.invoke(app, ["report", "--session", str(session), "--json"]).exit_code == 0


def test_usage_and_missing_report_are_json(session: Path) -> None:
    for command in ("submit", "report"):
        result = runner.invoke(app, [command, "--unknown", "--json"])
        assert result.exit_code == 2
        assert "error" in json.loads(result.stdout)
        assert result.stderr == ""
    missing = runner.invoke(app, ["report", "--session", str(session), "--json"])
    assert missing.exit_code == 2
    assert "not submitted" in json.loads(missing.stdout)["error"]["message"]


def test_unexpected_errors_do_not_leak_detail() -> None:
    with patch(
        "patchground.cli.reports.submit_session", side_effect=RuntimeError("private-detail")
    ):
        result = runner.invoke(app, ["submit", "--json"])
    assert result.exit_code == 2
    assert "private-detail" not in result.output
    assert json.loads(result.stdout)["error"]["kind"] == "internal"


def test_terminal_report_is_plain_text_and_saved_markdown_stays_escaped(
    session: Path, sandbox
) -> None:
    sandbox.result = RunResult(
        RunOutcome.PASSED,
        (TestResult("tests.test_x::test_a_b", "test_a_b", "tests.test_x", TestStatus.PASSED),),
        0,
        None,
        "",
    )
    with patch("patchground.sandbox.run_check", side_effect=sandbox.run_check):
        submitted = runner.invoke(app, ["submit", "--session", str(session)])
    assert "tests.test_x::test_a_b" in submitted.stdout
    assert "\\_" not in submitted.stdout
    assert "Attempt complete" in submitted.stdout
    saved = (session / ".session/submission/report.md").read_text()
    assert "test\\_a\\_b" in saved
    shown = runner.invoke(app, ["report", "--session", str(session)])
    assert "tests.test_x::test_a_b" in shown.stdout and "\\_" not in shown.stdout
    assert "Attempt complete" not in shown.stdout
