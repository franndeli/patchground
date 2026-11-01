"""Exercise the registered application rather than command-local test apps."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from patchground.cli.app import app

EXAMPLES = Path(__file__).resolve().parents[3] / "examples"


def test_discovery_commands_registered():
    runner = CliRunner()
    listed = runner.invoke(app, ["list", str(EXAMPLES), "--lang", "python", "--json"])
    assert listed.exit_code == 0
    assert {item["id"] for item in json.loads(listed.stdout)["challenges"]} == {
        "pagination-last-page",
        "duplicate-charges-on-retry",
        "cache-expiry",
        "csv-import-row-errors",
        "order-notifications-boundary",
    }
    shown = runner.invoke(app, ["show", str(EXAMPLES / "pagination-last-page"), "--json"])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["valid"] is True


@pytest.mark.parametrize("command", ["doctor", "list", "show", "reset"])
def test_registered_usage_errors_are_json(command):
    result = CliRunner().invoke(app, [command, "--unknown-option", "--json"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["kind"] == "environment"
    assert not result.stderr
