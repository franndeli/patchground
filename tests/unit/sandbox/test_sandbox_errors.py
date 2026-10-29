"""Error mapping of the sandbox, exercised with fake engine objects (no Docker needed)."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import docker.errors
import pytest
import requests
import urllib3.exceptions

from patchground.sandbox import BuildFailed, Limits, RunOutcome, SandboxError
from patchground.sandbox import build as sandbox_build
from patchground.sandbox import run as sandbox_run

# --------------------------------------------------------------------------- seed tar


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_unreadable_layer_file_is_a_sandbox_error(tmp_path: Path) -> None:
    secret = tmp_path / "ws" / "locked.py"
    secret.parent.mkdir()
    secret.write_text("x = 1\n")
    secret.chmod(0o000)
    try:
        with pytest.raises(SandboxError, match="cannot read files to copy"):
            sandbox_run.build_seed_tar([tmp_path / "ws"])
    finally:
        secret.chmod(0o644)


# --------------------------------------------------------------------------- run: wait()


class FakeContainer:
    """Just enough of a docker Container for ``_wait_and_collect``'s timeout decision."""

    def __init__(self, wait_error: Exception, wait_seconds: float = 0.0) -> None:
        self.wait_error = wait_error
        self.wait_seconds = wait_seconds
        self.killed = False
        self.attrs: dict[str, Any] = {"State": {"OOMKilled": False}}

    def wait(self, timeout: float) -> dict[str, int]:
        time.sleep(self.wait_seconds)
        raise self.wait_error

    def kill(self) -> None:
        self.killed = True

    def reload(self) -> None:
        pass

    def logs(self, **_: Any) -> bytes:
        return b"some output\n"


@pytest.mark.parametrize(
    "error", [requests.exceptions.ConnectionError("gone"), requests.exceptions.ReadTimeout("t/o")]
)
def test_connection_lost_early_is_not_a_timeout(error: Exception) -> None:
    container = FakeContainer(error)
    with pytest.raises(SandboxError, match="engine connection lost during run"):
        sandbox_run._wait_and_collect(container, Limits(timeout_seconds=60))
    assert not container.killed


@pytest.mark.parametrize(
    "error", [requests.exceptions.ConnectionError("gone"), requests.exceptions.ReadTimeout("t/o")]
)
def test_connection_error_at_deadline_is_a_timeout(error: Exception) -> None:
    # Deadline 1.2 s with 1 s tolerance: anything after 0.2 s counts as the limit being hit.
    container = FakeContainer(error, wait_seconds=0.3)
    result = sandbox_run._wait_and_collect(container, Limits(timeout_seconds=1.2))
    assert container.killed
    assert result.outcome is RunOutcome.LIMIT_EXCEEDED
    assert result.limit == "timeout"
    assert result.exit_code is None


# --------------------------------------------------------------------------- build


class FakeApi:
    def __init__(self, behaviour: Any) -> None:
        self.behaviour = behaviour
        self.kwargs: dict[str, Any] = {}

    def build(self, **kwargs: Any) -> Iterator[Any]:
        self.kwargs = kwargs
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        return self.behaviour()


class FakeImage:
    id = "sha256:" + "a" * 64


class FakeImages:
    def get(self, image_id: str) -> FakeImage:
        assert image_id == FakeImage.id
        return FakeImage()


class FakeClient:
    def __init__(self, behaviour: Any) -> None:
        self.api = FakeApi(behaviour)
        self.images = FakeImages()
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def dockerfile(tmp_path: Path) -> Path:
    path = tmp_path / "environment" / "Dockerfile"
    path.parent.mkdir()
    path.write_text("FROM scratch\n")
    return path


def _use(monkeypatch: pytest.MonkeyPatch, behaviour: Any) -> FakeClient:
    client = FakeClient(behaviour)
    monkeypatch.setattr(sandbox_build, "connect", lambda: client)
    return client


def _api_error(status: int | None) -> docker.errors.APIError:
    response = None
    if status is not None:
        response = requests.Response()
        response.status_code = status
    return docker.errors.APIError("boom", response=response, explanation="engine said no")


def test_build_success_reads_aux_id(monkeypatch: pytest.MonkeyPatch, dockerfile: Path) -> None:
    def chunks() -> Iterator[Any]:
        yield {"stream": "Step 1/1 : FROM scratch\n"}
        yield {"aux": {"ID": FakeImage.id}}

    client = _use(monkeypatch, chunks)
    result = sandbox_build.build_image(dockerfile, name="x", timeout_seconds=30)
    assert result.image_id == FakeImage.id
    assert "Step 1/1" in result.log
    assert client.api.kwargs["timeout"] == 30
    assert client.closed


def test_build_error_chunk_is_build_failed(
    monkeypatch: pytest.MonkeyPatch, dockerfile: Path
) -> None:
    def chunks() -> Iterator[Any]:
        yield {"stream": "Step 1/2 : RUN false\n"}
        yield {"error": "The command '/bin/sh -c false' returned a non-zero code: 1"}

    _use(monkeypatch, chunks)
    with pytest.raises(BuildFailed) as info:
        sandbox_build.build_image(dockerfile, name="x")
    assert "non-zero code: 1" in info.value.log


@pytest.mark.parametrize("status", [400, 404])
def test_build_client_error_is_build_failed(
    monkeypatch: pytest.MonkeyPatch, dockerfile: Path, status: int
) -> None:
    _use(monkeypatch, _api_error(status))
    with pytest.raises(BuildFailed) as info:
        sandbox_build.build_image(dockerfile, name="x")
    assert "engine said no" in info.value.log


@pytest.mark.parametrize("status", [500, 503, None])
def test_build_server_error_is_environment_error(
    monkeypatch: pytest.MonkeyPatch, dockerfile: Path, status: int | None
) -> None:
    _use(monkeypatch, _api_error(status))
    with pytest.raises(SandboxError, match="image build did not complete") as info:
        sandbox_build.build_image(dockerfile, name="x")
    assert not isinstance(info.value, BuildFailed)


@pytest.mark.parametrize(
    "error",
    [
        requests.exceptions.ConnectionError("gone"),
        urllib3.exceptions.ProtocolError("Connection broken"),
    ],
)
def test_build_connection_lost_early_is_environment_error(
    monkeypatch: pytest.MonkeyPatch, dockerfile: Path, error: Exception
) -> None:
    _use(monkeypatch, error)
    with pytest.raises(SandboxError, match="engine connection lost during build") as info:
        sandbox_build.build_image(dockerfile, name="x", timeout_seconds=60)
    assert not isinstance(info.value, BuildFailed)


@pytest.mark.parametrize(
    "error",
    [
        requests.exceptions.ConnectionError("read timed out"),
        requests.exceptions.ReadTimeout("read timed out"),
        urllib3.exceptions.ReadTimeoutError(None, None, "Read timed out."),
    ],
)
def test_build_read_timeout_at_deadline_is_build_failed(
    monkeypatch: pytest.MonkeyPatch, dockerfile: Path, error: Exception
) -> None:
    def chunks() -> Iterator[Any]:
        yield {"stream": "Step 1/2 : RUN sleep 60\n"}
        time.sleep(0.3)
        raise error

    _use(monkeypatch, chunks)
    with pytest.raises(BuildFailed, match=r"image build exceeded 1.2 s") as info:
        sandbox_build.build_image(dockerfile, name="x", timeout_seconds=1.2)
    assert "RUN sleep 60" in info.value.log
    assert "[patchground] image build exceeded 1.2 s" in info.value.log


def test_build_deadline_checked_while_output_streams(
    monkeypatch: pytest.MonkeyPatch, dockerfile: Path
) -> None:
    def chunks() -> Iterator[Any]:
        while True:  # a chatty build never trips the read timeout
            time.sleep(0.05)
            yield {"stream": "still going\n"}

    _use(monkeypatch, chunks)
    started = time.monotonic()
    with pytest.raises(BuildFailed, match=r"image build exceeded 0.3 s"):
        sandbox_build.build_image(dockerfile, name="x", timeout_seconds=0.3)
    assert time.monotonic() - started < 5


def test_build_rejects_non_positive_timeout(dockerfile: Path) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        sandbox_build.build_image(dockerfile, name="x", timeout_seconds=0)
