from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from patchground.spec import export_schemas
from patchground.spec.schema import main

REPO_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schema"
FILES = ["challenge-0.1.schema.json", "pack-0.1.schema.json"]


def objects(node: Any) -> list[dict[str, Any]]:
    """Every JSON Schema object definition (``type: object``) in ``node``."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            found.append(node)
        for value in node.values():
            found.extend(objects(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(objects(value))
    return found


def test_export_is_deterministic(tmp_path: Path) -> None:
    first = export_schemas(tmp_path / "a")
    second = export_schemas(tmp_path / "b")
    assert [p.name for p in first] == FILES
    for a, b in zip(first, second, strict=True):
        assert a.read_bytes() == b.read_bytes()
        assert a.read_text(encoding="utf-8").endswith("}\n")


def test_committed_schemas_are_up_to_date(tmp_path: Path) -> None:
    for path in export_schemas(tmp_path):
        committed = REPO_SCHEMA_DIR / path.name
        assert committed.read_bytes() == path.read_bytes(), (
            f"{committed} is stale; run `uv run python -m patchground.spec.schema schema`"
        )


def test_schema_headers_and_extension_rule(tmp_path: Path) -> None:
    for path in export_schemas(tmp_path):
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == f"https://patchground.dev/schema/{path.name}"
        assert "do not edit" in schema["$comment"]
        assert schema["title"]
        found = objects(schema)
        assert found, "expected object definitions"
        for obj in found:
            assert obj["additionalProperties"] is False
            assert obj["patternProperties"] == {"^x-": {}}


def test_challenge_schema_details(tmp_path: Path) -> None:
    export_schemas(tmp_path)
    schema = json.loads((tmp_path / FILES[0]).read_text(encoding="utf-8"))
    assert schema["$defs"]["ChallengeType"]["enum"] == ["debug", "feature", "review", "refactor"]
    assert schema["$defs"]["AIPolicy"]["enum"] == ["allowed", "forbidden"]
    assert schema["then"]["required"] == ["generated_by"]
    defs = {name for name, d in schema["$defs"].items() if d.get("type") == "object"}
    assert defs == {"Author", "Checks", "Debrief", "Environment", "GeneratedBy"}


def test_cli_main(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == FILES
