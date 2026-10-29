"""Connection to the container engine (Docker, or Podman via its Docker-compatible socket)."""

from __future__ import annotations

import docker
import docker.errors
import requests

from patchground.sandbox.errors import EngineUnavailable


def connect() -> docker.DockerClient:
    """Return a client for the engine configured in the environment, or raise EngineUnavailable."""
    try:
        client = docker.from_env()
    except docker.errors.DockerException as exc:
        raise EngineUnavailable(f"container engine not reachable: {exc}") from exc
    try:
        client.ping()
    except (docker.errors.DockerException, requests.exceptions.RequestException) as exc:
        client.close()
        raise EngineUnavailable(f"container engine not reachable: {exc}") from exc
    return client
