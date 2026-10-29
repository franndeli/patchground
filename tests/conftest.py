"""Shared pytest configuration: skip Docker tests when no engine is reachable."""

from __future__ import annotations

import functools

import pytest


@functools.cache
def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip = pytest.mark.skip(reason="Docker engine not reachable")
    for item in items:
        if "docker" in item.keywords and not _docker_available():
            item.add_marker(skip)
