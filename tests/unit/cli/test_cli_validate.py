"""Unit tests for `pgnd validate` (validate_challenge monkeypatched; no Docker)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from patchground.cli import validate as validate_cli
from patchground.cli.app import app
from patchground.verify import (
    StepName,
    StepResult,
    StepStatus,
    ValidationReport,
    VerifyEnvironmentError,
)

REPO = Path(__file__).resolve().parents[3]
runner = CliRunner()


def make_report(failed: StepName | None, verification_file: Path | None = None) -> ValidationReport:
    steps: list[StepResult] = []
    state = StepStatus.PASSED
    for name in StepName:
        if name in (StepName.DETERMINISM, StepName.ANTI_GAMING):
            steps.append(StepResult(name, StepStatus.NOT_RUN, "planned for M2"))
        elif name is failed:
            steps.append(StepResult(name, StepStatus.FAILED, f"{name.value} broke [red]x[/]"))
            state = StepStatus.NOT_RUN
        else:
            detail = "ok" if state is StepStatus.PASSED else "not run"
            steps.append(StepResult(name, state, detail, "t0", "t1"))
    return ValidationReport(
        folder=Path("c"),
        steps=tuple(steps),
        validated_at="t1",
        verification_file=verification_file,
    )


def fake(
    monkeypatch: pytest.MonkeyPatch, outcome: ValidationReport | BaseException
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def validate_challenge(folder: Path, **kwargs: Any) -> ValidationReport:
        calls.append({"folder": folder, **kwargs})
        kwargs["progress"]("building image")
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(validate_cli, "validate_challenge", validate_challenge)
    return calls


def test_valid_exits_0(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake(monkeypatch, make_report(None, Path("c/verification.json")))
    result = runner.invoke(app, ["validate", "c"])
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[-1] == "valid"
    assert lines[0].startswith("✓ manifest")
    assert "wrote c/verification.json" in result.stdout
    assert "building image" in result.stderr
    assert "building image" not in result.stdout
    assert calls[0]["folder"] == Path("c")
    assert calls[0]["write"] is True


def test_no_write_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake(monkeypatch, make_report(None))
    result = runner.invoke(app, ["validate", "c", "--no-write"])
    assert result.exit_code == 0
    assert calls[0]["write"] is False


def test_failed_step_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, make_report(StepName.BROKEN_FAILS))
    result = runner.invoke(app, ["validate", "c"])
    assert result.exit_code == 1
    lines = result.stdout.splitlines()
    assert lines[-1] == "invalid: failed at step broken_fails"
    assert any(line.startswith("✗ broken_fails") for line in lines)
    assert "broken_fails broke [red]x[/]" in result.stdout  # details are not Rich markup
    assert any(line.startswith("- determinism") and "planned for M2" in line for line in lines)


def test_json_success_is_one_document(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, make_report(None, Path("c/verification.json")))
    result = runner.invoke(app, ["validate", "c", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["valid"] is True
    assert doc["failed_step"] is None
    assert doc["verification_file"] == "c/verification.json"
    assert [s["name"] for s in doc["steps"]] == [n.value for n in StepName]
    assert result.stderr == ""  # no progress output in JSON mode


def test_json_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, make_report(StepName.REFERENCE_PASSES))
    result = runner.invoke(app, ["validate", "c", "--json"])
    assert result.exit_code == 1
    doc = json.loads(result.stdout)
    assert doc["valid"] is False
    assert doc["failed_step"] == "reference_passes"
    assert doc["verification_file"] is None


@pytest.mark.parametrize("json_mode", [False, True])
def test_environment_error_exits_2(monkeypatch: pytest.MonkeyPatch, json_mode: bool) -> None:
    fake(monkeypatch, VerifyEnvironmentError("container engine unavailable: no socket"))
    result = runner.invoke(app, ["validate", "c", *(["--json"] if json_mode else [])])
    assert result.exit_code == 2
    if json_mode:
        assert json.loads(result.stdout) == {
            "error": {"kind": "environment", "message": "container engine unavailable: no socket"}
        }
    else:
        assert result.stdout == ""
        assert "error: container engine unavailable: no socket" in result.stderr


def test_usage_error_exits_2() -> None:
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 2


def test_invalid_manifest_fixture_names_file_and_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    result = runner.invoke(app, ["validate", "tests/fixtures/invalid-manifest"])
    assert result.exit_code == 1
    out = result.stdout
    prefix = "tests/fixtures/invalid-manifest/challenge.yaml"
    assert f"{prefix}:1: timebox_minutes: field required" in out
    assert f"{prefix}:5: type: " in out
    assert f"{prefix}:12: estimated_minutes: unknown key" in out
    assert f"{prefix}:17: environment.network: unknown key" in out
    assert ":24:" not in out
    assert out.splitlines()[-1] == "invalid: failed at step manifest"
    assert not (REPO / "tests/fixtures/invalid-manifest/verification.json").exists()


def test_invalid_manifest_fixture_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    result = runner.invoke(app, ["validate", "tests/fixtures/invalid-manifest", "--json"])
    assert result.exit_code == 1
    doc = json.loads(result.stdout)
    assert doc["failed_step"] == "manifest"
    issues = doc["steps"][0]["issues"]
    assert [i["line"] for i in issues] == [1, 5, 12, 17]
    assert issues[1]["text"].startswith("tests/fixtures/invalid-manifest/challenge.yaml:5: type:")


@pytest.mark.parametrize("json_mode", [False, True])
def test_unexpected_error_exits_2_without_traceback(
    monkeypatch: pytest.MonkeyPatch, json_mode: bool
) -> None:
    fake(monkeypatch, RuntimeError("something broke"))
    result = runner.invoke(app, ["validate", "c", *(["--json"] if json_mode else [])])
    assert result.exit_code == 2
    assert "Traceback" not in result.output
    if json_mode:
        assert json.loads(result.stdout) == {
            "error": {"kind": "internal", "message": "RuntimeError: something broke"}
        }
    else:
        assert result.stdout == ""
        assert "error: RuntimeError: something broke" in result.stderr


def test_keyboard_interrupt_exits_130(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, KeyboardInterrupt())
    result = runner.invoke(app, ["validate", "c", "--json"])
    assert result.exit_code == 130
    assert json.loads(result.stdout)["error"]["kind"] == "interrupted"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_read_only_folder_with_stale_record_exits_2_with_one_json_doc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Real validate_challenge: the manifest step fails, then the stale record cannot be removed.
    folder = tmp_path / "broken"
    folder.mkdir()
    (folder / "challenge.yaml").write_text("id: broken\n")
    stale = folder / "verification.json"
    stale.write_text('{"format": "patchground-verification", "format_version": 1}\n')
    folder.chmod(0o555)
    try:
        result = runner.invoke(app, ["validate", str(folder), "--json"])
    finally:
        folder.chmod(0o755)
    assert result.exit_code == 2
    doc = json.loads(result.stdout)
    assert doc["error"]["kind"] == "environment"
    assert "could not be removed" in doc["error"]["message"]
    assert stale.exists()
