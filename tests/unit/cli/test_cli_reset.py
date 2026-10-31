"""Confirmation cannot be bypassed accidentally in JSON mode."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from patchground.cli import sessions
from patchground.cli.app import app
from patchground.sessions import ResetResult


@pytest.mark.parametrize(
    "args,answer,expected,calls_expected",
    [
        (["--json"], None, 2, 0),
        (["--json", "--yes"], None, 0, 1),
        ([], "n\n", 130, 0),
        ([], "y\n", 0, 1),
    ],
)
def test_confirmation(monkeypatch, args, answer, expected, calls_expected):
    calls = []

    def reset(session):
        calls.append(session)
        return ResetResult(
            session=Path("selected"), workspace=Path("selected/workspace"), challenge_id="sample"
        )

    monkeypatch.setattr(sessions, "reset_session", reset)
    result = CliRunner().invoke(app, ["reset", *args], input=answer)
    assert result.exit_code == expected
    assert len(calls) == calls_expected
    if "--json" in args:
        assert isinstance(json.loads(result.stdout), dict)
        assert not result.stderr
