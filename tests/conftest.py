"""Shared pytest configuration: skip Docker tests when no engine is reachable.

With ``PATCHGROUND_REQUIRE_DOCKER=1`` (set in CI's docker job) an unreachable engine fails the
run instead, so the integration suite can never silently pass by skipping everything.
"""

from __future__ import annotations

import functools
import os
import subprocess
from pathlib import Path

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


@pytest.fixture
def pack_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A committed runnable pack and isolated CLI home; no developer Git settings."""
    from patchground.authoring import create_challenge
    from patchground.safeio import resolve_git

    executable = resolve_git(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    repo = tmp_path / "source"
    repo.mkdir()
    with monkeypatch.context() as context:
        context.chdir(repo)
        create_challenge("pack-exercise")
    (repo / "pack.yaml").write_text(
        'spec_version: "0.1"\nname: sample-pack\nversion: 1.0.0\n'
        "description: Test pack\nchallenges: [pack-exercise]\n"
    )
    env = {
        "PATH": os.defpath,
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }

    def git(*arguments: str) -> str:
        return subprocess.run(
            [
                executable,
                "-c",
                "core.hooksPath=" + os.devnull,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=0+tests@users.noreply.github.com",
                *arguments,
            ],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    git("init", "--template=", "--initial-branch=main")
    git("add", "--all")
    git("commit", "-m", "Create test pack")
    return repo, git
