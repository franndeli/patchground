"""Combine parsed settings for the deployment preview."""

from collections.abc import Mapping, Sequence
from typing import TypedDict


class Layer(TypedDict):
    priority: int
    values: Mapping[str, object]


def merge_layers(layers: Sequence[Layer]) -> dict[str, object]:
    """Return the effective top-level settings without modifying layers."""
    merged: dict[str, object] = {}
    for layer in sorted(layers, key=lambda layer: layer["priority"], reverse=True):
        for key, value in layer["values"].items():
            if value and key not in merged:
                merged[key] = value
    return merged
