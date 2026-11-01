"""The portable recipe is packaged data, with no optional runtime imports."""

import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from patchground.runner_assets import VITEST_COMMAND, vitest_assets


def test_assets_are_canonical_portable_bytes() -> None:
    assets = vitest_assets()
    assert set(assets) == {"Dockerfile", "package.json", "package-lock.json", "vitest-runner.mjs"}
    for name, data in assets.items():
        assert "/" not in name and "\\" not in name
        assert isinstance(data, bytes) and data.endswith(b"\n")
        assert b"\r" not in data
        assert data == files("patchground.runner_assets").joinpath(name).read_bytes()
    assets.clear()
    assert len(vitest_assets()) == 4
    assert VITEST_COMMAND == "node /opt/patchground/vitest-runner.mjs"


def test_curated_typescript_environments_match_canonical_assets() -> None:
    examples = Path(__file__).resolve().parents[3] / "examples"
    for challenge in ("release-version-ordering", "event-bus-subscriptions"):
        for name, data in vitest_assets().items():
            assert (examples / challenge / "environment" / name).read_bytes() == data


def test_locked_build_time_recipe() -> None:
    assets = vitest_assets()
    package = json.loads(assets["package.json"])
    lock = json.loads(assets["package-lock.json"])
    assert package["dependencies"] == {"vitest": "5.0.5", "vite": "8.3.5"}
    assert lock["lockfileVersion"] == 3
    assert lock["packages"][""]["dependencies"] == package["dependencies"]
    for name, metadata in lock["packages"].items():
        if name:
            assert metadata["integrity"].startswith("sha512-")
            assert metadata["resolved"].startswith("https://registry.npmjs.org/")
    dockerfile = assets["Dockerfile"].decode()
    assert "node:24.15.0-bookworm-slim@sha256:" in dockerfile
    assert "npm ci --ignore-scripts --no-audit --no-fund" in dockerfile
    assert "COPY ." not in dockerfile


def test_import_is_safe_without_ai_or_engine() -> None:
    code = """
import importlib.abc
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('patchground.ai', 'patchground.sandbox', 'docker', 'litellm')):
            raise AssertionError('unexpected optional or execution import')
sys.meta_path.insert(0, Block())
from patchground.runner_assets import VITEST_COMMAND, vitest_assets
assert VITEST_COMMAND and len(vitest_assets()) == 4
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, check=False)
    assert result.returncode == 0
    assert not result.stdout and not result.stderr
