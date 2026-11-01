"""Canonical container-only runner resources; importing never executes a runner."""

from importlib.resources import files

VITEST_COMMAND = "node /opt/patchground/vitest-runner.mjs"

_ASSETS = ("Dockerfile", "package.json", "package-lock.json", "vitest-runner.mjs")


def vitest_assets() -> dict[str, bytes]:
    """Return independent, portable copies of the canonical environment resources."""
    resources = files(__package__)
    return {name: resources.joinpath(name).read_bytes() for name in _ASSETS}


__all__ = ["VITEST_COMMAND", "vitest_assets"]
