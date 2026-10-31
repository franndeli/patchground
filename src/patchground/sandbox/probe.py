"""Engine probing for `doctor`: reachable, version. Never builds, pulls or runs anything."""

from __future__ import annotations

import errno
import socket
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import docker
import docker.errors
import requests

DEFAULT_PROBE_TIMEOUT = 5.0


class EngineProblem(StrEnum):
    """Why the engine could not be used; a category, never the raw engine error."""

    NOT_RUNNING = "not_running"  # no socket, connection refused: engine absent or stopped
    PERMISSION = "permission"  # socket exists but this user may not use it
    TIMEOUT = "timeout"  # engine did not answer within the probe budget
    MISCONFIGURED = "misconfigured"  # DOCKER_HOST / context could not be parsed or used
    UNHEALTHY = "unhealthy"  # engine answered, but with an error


@dataclass(frozen=True)
class EngineProbe:
    """Structured engine readiness. ``problem`` is None exactly when ``reachable``."""

    reachable: bool
    problem: EngineProblem | None = None
    engine: str | None = None  # "Docker" or "Podman"
    version: str | None = None
    api_version: str | None = None


def probe_engine(*, timeout: float = DEFAULT_PROBE_TIMEOUT) -> EngineProbe:
    """Ping the configured engine and read its version, within ``timeout`` seconds per request.

    Never raises for an unusable engine; the client is always closed.
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    client: docker.DockerClient | None = None
    try:
        client = docker.from_env(timeout=max(1, round(timeout)))
        client.ping()
        info: dict[str, Any] = client.version()
    except (docker.errors.DockerException, requests.exceptions.RequestException, OSError) as exc:
        return EngineProbe(reachable=False, problem=_classify(exc))
    finally:
        if client is not None:
            client.close()
    return EngineProbe(
        reachable=True,
        engine=_engine_name(info),
        version=_text(info.get("Version")),
        api_version=_text(info.get("ApiVersion")),
    )


def _text(value: object) -> str | None:
    return value[:64] if isinstance(value, str) and value else None


def _engine_name(info: dict[str, Any]) -> str:
    components = info.get("Components")
    if isinstance(components, list):
        for component in components:
            name = component.get("Name") if isinstance(component, dict) else None
            if isinstance(name, str) and "podman" in name.lower():
                return "Podman"
    return "Docker"


def _chain(exc: BaseException) -> list[BaseException]:
    """The exception, its causes/contexts and exceptions nested in args (bounded)."""
    seen: list[BaseException] = []
    pending: list[BaseException] = [exc]
    while pending and len(seen) < 32:
        current = pending.pop()
        if any(current is known for known in seen):
            continue
        seen.append(current)
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
        for arg in current.args:
            nested = arg if isinstance(arg, tuple) else (arg,)
            pending.extend(item for item in nested if isinstance(item, BaseException))
    return seen


def _classify(exc: BaseException) -> EngineProblem:
    chain = _chain(exc)
    for item in chain:
        if isinstance(item, PermissionError) or (
            isinstance(item, OSError) and item.errno in (errno.EACCES, errno.EPERM)
        ):
            return EngineProblem.PERMISSION
    for item in chain:
        if isinstance(item, (requests.exceptions.Timeout, socket.timeout, TimeoutError)):
            return EngineProblem.TIMEOUT
    for item in chain:
        if isinstance(item, (FileNotFoundError, ConnectionRefusedError, ConnectionResetError)):
            return EngineProblem.NOT_RUNNING
        if isinstance(item, requests.exceptions.ConnectionError):
            return EngineProblem.NOT_RUNNING
    if isinstance(exc, docker.errors.APIError):
        return EngineProblem.UNHEALTHY
    if (
        isinstance(exc, docker.errors.DockerException)
        and "fetching server api version" in str(exc).lower()
    ):
        return EngineProblem.NOT_RUNNING
    return EngineProblem.MISCONFIGURED
