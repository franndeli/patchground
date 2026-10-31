"""Engine probing without a real engine: every failure becomes a category, never raw text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import docker
import docker.errors
import pytest
import requests

from patchground.sandbox import EngineProblem, probe_engine
from patchground.sandbox import probe as probe_module


class FakeClient:
    def __init__(self, *, ping_error: BaseException | None = None, version: Any = None) -> None:
        self.ping_error = ping_error
        self.info = version if version is not None else {"Version": "27.1.0", "ApiVersion": "1.46"}
        self.closed = False

    def ping(self) -> bool:
        if self.ping_error is not None:
            raise self.ping_error
        return True

    def version(self) -> Any:
        return self.info

    def close(self) -> None:
        self.closed = True


def _install(monkeypatch: pytest.MonkeyPatch, client: FakeClient, timeouts: list[int]) -> None:
    def from_env(*, timeout: int) -> FakeClient:
        timeouts.append(timeout)
        return client

    monkeypatch.setattr(probe_module.docker, "from_env", from_env)


def test_reachable_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    client, timeouts = FakeClient(), []
    _install(monkeypatch, client, timeouts)
    probe = probe_engine(timeout=3)
    assert probe.reachable and probe.problem is None
    assert (probe.engine, probe.version, probe.api_version) == ("Docker", "27.1.0", "1.46")
    assert client.closed and timeouts == [3]


def test_reachable_podman(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(version={"Version": "5.0", "Components": [{"Name": "Podman Engine"}]})
    _install(monkeypatch, client, [])
    assert probe_engine().engine == "Podman"


def _wrapped(inner: BaseException) -> docker.errors.DockerException:
    try:
        try:
            raise requests.exceptions.ConnectionError(("Connection aborted.", inner))
        except requests.exceptions.ConnectionError as exc:
            raise docker.errors.DockerException("Error while fetching server API version") from exc
    except docker.errors.DockerException as outer:
        return outer


@pytest.mark.parametrize(
    ("error", "problem"),
    [
        (_wrapped(FileNotFoundError(2, "secret-path")), EngineProblem.NOT_RUNNING),
        (_wrapped(ConnectionRefusedError()), EngineProblem.NOT_RUNNING),
        (_wrapped(PermissionError(13, "denied")), EngineProblem.PERMISSION),
        (requests.exceptions.ReadTimeout(), EngineProblem.TIMEOUT),
        (docker.errors.DockerException("bad DOCKER_HOST"), EngineProblem.MISCONFIGURED),
    ],
)
def test_ping_failures_close_client(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, problem: EngineProblem
) -> None:
    client = FakeClient(ping_error=error)
    _install(monkeypatch, client, [])
    probe = probe_engine()
    assert not probe.reachable and probe.problem is problem
    assert client.closed


def test_api_error_is_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(ping_error=docker.errors.APIError("500 Server Error"))
    _install(monkeypatch, client, [])
    assert probe_engine().problem is EngineProblem.UNHEALTHY


def test_client_creation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def from_env(*, timeout: int) -> FakeClient:
        raise _wrapped(FileNotFoundError())

    monkeypatch.setattr(probe_module.docker, "from_env", from_env)
    assert probe_engine().problem is EngineProblem.NOT_RUNNING


def test_missing_socket_with_real_sdk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DOCKER_HOST", f"unix://{tmp_path}/no-such.sock")
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    probe = probe_engine(timeout=2)
    assert not probe.reachable and probe.problem is EngineProblem.NOT_RUNNING


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        probe_engine(timeout=0)
