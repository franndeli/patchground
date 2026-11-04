"""The approved interview batch must be usable content, not just a proposed list."""

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from patchground.cli.app import app
from patchground.spec import Provenance, load_challenge

ROOT = Path(__file__).resolve().parents[2]
BATCH = {
    "config-precedence": ("python", "debug", "beginner", 30),
    "draft-edit-isolation": ("typescript", "debug", "beginner", 30),
    "cron-field-expansion": ("python", "feature", "intermediate", 60),
    "invoice-monthly-summary": ("python", "debug", "intermediate", 45),
    "sliding-window-rate-limit": ("typescript", "feature", "intermediate", 45),
    "search-response-ordering": ("typescript", "debug", "intermediate", 45),
    "webhook-retry-scheduling": ("python", "feature", "advanced", 75),
    "transaction-rule-evaluator": ("typescript", "feature", "advanced", 75),
}


def test_approved_batch_is_discoverable_outside_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["list", "--builtin", "--json"])
    assert result.exit_code == 0
    found = {entry["id"] for entry in json.loads(result.stdout)["challenges"]}
    missing = BATCH.keys() - found
    assert not missing, f"Implement the missing challenges under examples/: {sorted(missing)}"


@pytest.mark.parametrize("challenge_id", BATCH)
def test_approved_challenge_has_complete_metadata_and_authoring_materials(challenge_id):
    folder = ROOT / "examples" / challenge_id
    manifest = load_challenge(folder).manifest
    language, kind, difficulty, minutes = BATCH[challenge_id]
    assert manifest.languages == [language]
    assert manifest.type.value == kind
    assert manifest.difficulty.value == difficulty
    assert manifest.timebox_minutes == minutes
    assert manifest.provenance is Provenance.GENERATED
    assert manifest.generated_by is not None
    assert manifest.generated_by.prompt_version == "interview-batch-v1"
    assert manifest.hints
    assert manifest.debrief is not None
    assert manifest.debrief.questions is not None
    assert "tests/" in manifest.expected_paths
    assert (folder / "TICKET.md").stat().st_size > 0
    patch = (folder / manifest.solution).read_text()
    changed = re.findall(r"^\+\+\+ b/(.+)$", patch, re.MULTILINE)
    assert changed and all(path.startswith("src/") for path in changed), changed
