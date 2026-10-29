"""Shared pytest configuration: skip Docker tests when no engine is reachable.

With ``PATCHGROUND_REQUIRE_DOCKER=1`` (set in CI's docker job) an unreachable engine fails the
run instead, so the integration suite can never silently pass by skipping everything.
"""

from __future__ import annotations

import functools
import os

import pytest

REQUIRE_DOCKER_ENV = "PATCHGROUND_REQUIRE_DOCKER"


@functools.cache
def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    docker_items = [item for item in items if "docker" in item.keywords]
    if not docker_items or _docker_available():
        return
    if os.environ.get(REQUIRE_DOCKER_ENV) == "1":
        raise pytest.UsageError(
            f"{REQUIRE_DOCKER_ENV}=1 but the Docker engine is not reachable; "
            f"{len(docker_items)} docker test(s) cannot run"
        )
    skip = pytest.mark.skip(reason="Docker engine not reachable")
    for item in docker_items:
        item.add_marker(skip)
