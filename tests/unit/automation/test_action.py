from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[3]
ACTION = YAML(typ="safe").load((ROOT / "action.yml").read_text())
STEPS: list[dict[str, Any]] = ACTION["runs"]["steps"]


def test_composite_inputs_and_outputs() -> None:
    assert ACTION["runs"]["using"] == "composite"
    inputs = ACTION["inputs"]
    assert set(inputs) == {
        "source-directory",
        "challenge-directory",
        "base-commit",
        "allow-execution",
    }
    assert inputs["allow-execution"]["default"] == "false"
    assert inputs["source-directory"]["default"] == "${{ github.workspace }}"
    assert inputs["challenge-directory"]["default"] == "."
    assert "report-file" in ACTION["outputs"]


def test_third_party_actions_pinned_to_full_sha() -> None:
    uses = [s["uses"] for s in STEPS if "uses" in s]
    assert uses
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), ref


def test_no_untrusted_expression_interpolated_into_shell() -> None:
    for step in STEPS:
        script = step.get("run", "")
        assert "${{" not in script, script


def test_installs_locked_core_from_action_source() -> None:
    script = "\n".join(s.get("run", "") for s in STEPS)
    assert "uv sync --locked" in script and "--no-dev" in script
    assert "github.action_path" in str(STEPS)
    assert "--extra" not in script and "pip install" not in script


def test_runs_isolated_and_consent_is_conditional() -> None:
    run = next(s for s in STEPS if s.get("id") == "validate")
    script = run["run"]
    assert "-I -m patchground.automation" in script
    assert '"$ALLOW_EXECUTION" = "true"' in script
    assert script.count("--consent") == 1
    assert run["env"]["ALLOW_EXECUTION"] == "${{ inputs.allow-execution }}"


def test_report_output_set_before_execution_and_outside_checkout() -> None:
    script = next(s for s in STEPS if s.get("id") == "validate")["run"]
    assert script.index("report-file=") < script.index("exec ")
    assert "mktemp -d" in script and "REPORT_ROOT" in script
    assert "${{ runner.temp }}" in str(STEPS)


def test_event_base_only_used_as_sha() -> None:
    script = next(s for s in STEPS if s.get("id") == "validate")["run"]
    assert "([0-9a-f]{40}|[0-9a-f]{64})" in script and "0+" in script


def test_setup_uv_v7_and_unique_private_environment() -> None:
    assert any(s.get("uses", "").startswith("astral-sh/setup-uv@37802adc94f3") for s in STEPS)
    install = next(s for s in STEPS if s.get("id") == "install")
    assert "mktemp -d" in install["run"] and "venv-dir=" in install["run"]
    assert "--no-editable" in install["run"]
    validate = next(s for s in STEPS if s.get("id") == "validate")
    assert validate["env"]["VENV_DIR"] == "${{ steps.install.outputs.venv-dir }}"
    assert "patchground-action-venv" not in str(STEPS)


@pytest.mark.parametrize("nested_temp", [False, True])
def test_installation_protects_checkout_before_starting_tools(
    tmp_path: Path, nested_temp: bool
) -> None:
    checkout = tmp_path / "checkout"
    action = tmp_path / "trusted-action"
    tools = tmp_path / "tools"
    runner = tmp_path / "runner"
    for directory in (checkout, action, tools, runner):
        directory.mkdir()
    tool = tools / "uv"
    tool.write_text(
        "#!/bin/sh\n"
        '[ -z "${PYTHONPATH-}${PYTHONHOME-}${PYTHONSTARTUP-}${PYTHONINSPECT-}" ] || exit 91\n'
        '[ "$PWD" = "$ACTION_PATH" ] || exit 92\n'
        ': > "$CHECK_MARKER"\n'
    )
    tool.chmod(0o755)
    marker = runner / "safe-install"
    env = {
        **os.environ,
        "PATH": f"{tools}{os.pathsep}{os.defpath}",
        "ACTION_PATH": str(action),
        "ENV_ROOT": str(checkout if nested_temp else runner),
        "SOURCE_DIRECTORY": "checkout",
        "GITHUB_WORKSPACE": str(tmp_path),
        "GITHUB_OUTPUT": str(runner / "outputs"),
        "CHECK_MARKER": str(marker),
        "PYTHONPATH": str(checkout),
        "PYTHONHOME": str(checkout),
        "PYTHONSTARTUP": str(checkout / "startup.py"),
        "PYTHONINSPECT": "1",
    }
    script = next(s for s in STEPS if s.get("id") == "install")["run"]
    result = subprocess.run(
        ["bash", "-c", script], cwd=checkout, env=env, capture_output=True, check=False
    )
    assert result.returncode == (2 if nested_temp else 0)
    assert marker.exists() is not nested_temp
    assert list(checkout.iterdir()) == []
    if not nested_temp:
        outputs = dict(line.split("=", 1) for line in (runner / "outputs").read_text().splitlines())
        assert outputs["source-directory"] == str(checkout.resolve())
