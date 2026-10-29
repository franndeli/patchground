"""The docker-test gate in tests/conftest.py: skip without an engine, unless it is required."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCKER_TESTS = "tests/integration/test_sandbox_docker.py"


def _collect(tmp_path: Path, *, require: bool) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("DOCKER_CONTEXT",)}
    env["DOCKER_HOST"] = f"unix://{tmp_path}/no-such.sock"
    env.pop("PATCHGROUND_REQUIRE_DOCKER", None)
    if require:
        env["PATCHGROUND_REQUIRE_DOCKER"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs", DOCKER_TESTS],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_docker_tests_skip_without_engine(tmp_path: Path) -> None:
    result = _collect(tmp_path, require=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipped" in result.stdout
    assert "Docker engine not reachable" in result.stdout


def test_docker_tests_fail_without_engine_when_required(tmp_path: Path) -> None:
    result = _collect(tmp_path, require=True)
    assert result.returncode == 4, result.stdout + result.stderr  # pytest's usage-error code
    assert "PATCHGROUND_REQUIRE_DOCKER=1" in result.stdout + result.stderr
