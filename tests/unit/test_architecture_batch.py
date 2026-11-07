"""The architecture challenges ship as complete, discoverable built-in content."""

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from patchground.cli.app import app
from patchground.spec import ChallengeType, load_challenge

ROOT = Path(__file__).resolve().parents[2]
BATCH = {
    "order-notifications-boundary": ("python", "intermediate"),
    "sales-report-layers": ("python", "intermediate"),
    "shipping-carrier-plugins": ("typescript", "intermediate"),
    "payment-vendor-boundary": ("python", "advanced"),
}


def test_architecture_filter_lists_the_batch_outside_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["list", "--builtin", "--type", "architecture", "--json"])
    assert result.exit_code == 0
    assert {entry["id"] for entry in json.loads(result.stdout)["challenges"]} == BATCH.keys()


@pytest.mark.parametrize("challenge_id", BATCH)
def test_architecture_challenge_is_complete(challenge_id):
    folder = ROOT / "examples" / challenge_id
    manifest = load_challenge(folder).manifest
    language, difficulty = BATCH[challenge_id]
    assert manifest.type is ChallengeType.ARCHITECTURE
    assert manifest.languages == [language]
    assert manifest.difficulty.value == difficulty
    assert "architecture" in manifest.tags
    assert manifest.hints
    assert manifest.debrief is not None
    assert "tests/" in manifest.expected_paths
    assert manifest.checks.hidden is not None
    assert any((folder / manifest.checks.hidden).rglob("*"))
    patch = (folder / manifest.solution).read_text()
    changed = re.findall(r"^\+\+\+ b/(.+)$", patch, re.MULTILINE)
    assert changed and all(path.startswith("src/") for path in changed), changed
