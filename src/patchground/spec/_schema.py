"""JSON Schema export for the v0.1 manifests (public entry point: ``patchground.spec.schema``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from patchground.spec.models import SPEC_VERSION, ChallengeManifest, PackManifest

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_BASE_URL = "https://patchground.dev/schema/"
GENERATED_COMMENT = "Generated from patchground.spec.models; do not edit."

_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("challenge", ChallengeManifest),
    ("pack", PackManifest),
)


def schema_filename(kind: str) -> str:
    """File name of the exported schema for ``kind`` ("challenge" or "pack")."""
    return f"{kind}-{SPEC_VERSION}.schema.json"


def build_schema(kind: str, model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema (draft 2020-12) for ``model`` with the Patchground header fields."""
    body = model.model_json_schema(mode="validation")
    header: dict[str, Any] = {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": SCHEMA_BASE_URL + schema_filename(kind),
        "$comment": GENERATED_COMMENT,
        "title": body.pop("title", model.__name__),
    }
    return header | body


def render_schema(kind: str, model: type[BaseModel]) -> str:
    """Deterministic, pretty JSON text with a trailing newline."""
    return json.dumps(build_schema(kind, model), indent=2, ensure_ascii=False) + "\n"


def export_schemas(out_dir: Path) -> list[Path]:
    """Write ``challenge-<v>.schema.json`` and ``pack-<v>.schema.json`` into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for kind, model in _MODELS:
        path = out_dir / schema_filename(kind)
        path.write_text(render_schema(kind, model), encoding="utf-8", newline="\n")
        written.append(path)
    return written
