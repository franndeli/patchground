"""Integration tests for the sandbox against a real container engine."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from textwrap import dedent

import docker
import pytest
from docker.models.containers import Container

from patchground.sandbox import (
    BuildFailed,
    BuildResult,
    Limits,
    RunOutcome,
    RunResult,
    SandboxError,
    TestStatus,
    build_image,
    run_check,
)
from patchground.sandbox import run as sandbox_run

pytestmark = pytest.mark.docker

PYTEST = "python -m pytest -q -p no:cacheprovider --junitxml=$PG_RESULTS/junit.xml"


@pytest.fixture(scope="session")
def image(tmp_path_factory: pytest.TempPathFactory) -> BuildResult:
    env = tmp_path_factory.mktemp("environment")
    (env / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "RUN pip install --no-cache-dir pytest==8.3.5\n"
        # Owned by the run user but outside /workspace: only the read-only rootfs stops writes.
        "RUN mkdir /owned && chown 1000:1000 /owned\n"
    )
    return build_image(env / "Dockerfile", name="sandbox-test")


@pytest.fixture(scope="session")
def engine() -> Iterator[docker.DockerClient]:
    client = docker.from_env()
    yield client
    client.close()


def _workspace(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(content))
    return root


def _run(
    image: BuildResult, ws: Path, command: str = PYTEST, limits: Limits | None = None
) -> RunResult:
    return run_check(image.image_id, [ws], command, limits=limits or Limits())


def _assert_no_leftovers(engine: docker.DockerClient) -> None:
    label = {"label": "patchground=1"}
    assert engine.containers.list(all=True, filters=label) == []
    assert engine.networks.list(filters=label) == []
    assert engine.volumes.list(filters=label) == []


def test_build_is_tagged_by_context_hash(image: BuildResult) -> None:
    assert image.tag.startswith("patchground/sandbox-test:")
    assert len(image.tag.rsplit(":", 1)[1]) == 12
    assert image.image_id.startswith("sha256:")
    assert image.log


def test_build_failure_raises_with_log(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nRUN echo about-to-fail && exit 3\n"
    )
    with pytest.raises(BuildFailed) as info:
        build_image(tmp_path / "Dockerfile", name="sandbox-broken")
    assert "about-to-fail" in info.value.log
    assert "returned a non-zero code: 3" in info.value.log


def test_build_timeout(tmp_path: Path, engine: docker.DockerClient) -> None:
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nRUN echo before-sleep && sleep 60\n"
    )
    started = time.monotonic()
    with pytest.raises(BuildFailed, match="image build exceeded 5 s") as info:
        build_image(tmp_path / "Dockerfile", name="sandbox-slow", timeout_seconds=5)
    assert time.monotonic() - started < 30
    assert "[patchground] image build exceeded 5 s" in info.value.log
    # Closing the build connection makes the engine cancel the build and remove its
    # intermediate container (it may linger as "Dead" for a moment).
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        sleeping = [
            c
            for c in engine.containers.list(all=True)
            if "before-sleep" in " ".join(c.attrs.get("Config", {}).get("Cmd") or [])
        ]
        if not sleeping:
            break
        time.sleep(0.5)
    assert sleeping == []


def test_passing_run(image: BuildResult, tmp_path: Path, engine: docker.DockerClient) -> None:
    ws = _workspace(tmp_path / "ws", {"test_ok.py": "def test_ok():\n    assert 1 + 1 == 2\n"})
    result = _run(image, ws)
    assert result.outcome is RunOutcome.PASSED, result.log_tail
    assert [(t.id, t.status) for t in result.tests] == [("test_ok::test_ok", TestStatus.PASSED)]
    assert result.exit_code == 0
    assert result.limit is None
    assert "1 passed" in result.log_tail
    _assert_no_leftovers(engine)


def test_failing_run_with_hidden_layer(image: BuildResult, tmp_path: Path) -> None:
    ws = _workspace(tmp_path / "ws", {"app.py": "def add(a, b):\n    return a - b\n"})
    hidden = _workspace(
        tmp_path / "hidden",
        {
            "tests/test_hidden.py": """\
            from app import add


            def test_add():
                assert add(2, 2) == 4
            """
        },
    )
    result = run_check(
        image.image_id, [ws, hidden], f"PYTHONPATH=/workspace {PYTEST}", limits=Limits()
    )
    assert result.outcome is RunOutcome.FAILED, result.log_tail
    assert [(t.id, t.status) for t in result.tests] == [
        ("tests.test_hidden::test_add", TestStatus.FAILED)
    ]
    assert result.exit_code == 1


def test_missing_junit(image: BuildResult, tmp_path: Path) -> None:
    result = _run(image, _workspace(tmp_path / "ws", {}), "echo no results here")
    assert result.outcome is RunOutcome.MISSING_RESULTS
    assert result.exit_code == 0
    assert "no results here" in result.log_tail
    assert "junit.xml was not written" in result.log_tail


def test_unparsable_junit(image: BuildResult, tmp_path: Path) -> None:
    result = _run(image, _workspace(tmp_path / "ws", {}), "echo garbage > $PG_RESULTS/junit.xml")
    assert result.outcome is RunOutcome.MISSING_RESULTS
    assert "unusable" in result.log_tail


def test_symlinked_junit_is_not_followed(image: BuildResult, tmp_path: Path) -> None:
    result = _run(image, _workspace(tmp_path / "ws", {}), "ln -s /etc/passwd $PG_RESULTS/junit.xml")
    assert result.outcome is RunOutcome.MISSING_RESULTS
    assert "not a regular file" in result.log_tail


def test_zero_tests_is_errored(image: BuildResult, tmp_path: Path) -> None:
    result = _run(image, _workspace(tmp_path / "ws", {"test_none.py": "x = 1\n"}))
    assert result.outcome is RunOutcome.ERRORED
    assert "no test cases" in result.log_tail


def test_timeout(image: BuildResult, tmp_path: Path, engine: docker.DockerClient) -> None:
    started = time.monotonic()
    result = _run(image, _workspace(tmp_path / "ws", {}), "sleep 120", Limits(timeout_seconds=3))
    assert time.monotonic() - started < 60
    assert result.outcome is RunOutcome.LIMIT_EXCEEDED
    assert result.limit == "timeout"
    assert result.exit_code is None
    _assert_no_leftovers(engine)


def test_memory_limit(image: BuildResult, tmp_path: Path, engine: docker.DockerClient) -> None:
    result = _run(
        image,
        _workspace(tmp_path / "ws", {}),
        "python -c 'data = b\"x\" * (3 * 1024**3)'",
        Limits(memory_bytes=256 * 1024**2),
    )
    assert result.outcome is RunOutcome.LIMIT_EXCEEDED, result.log_tail
    assert result.limit == "memory"
    _assert_no_leftovers(engine)


def test_network_is_blocked(image: BuildResult, tmp_path: Path) -> None:
    ws = _workspace(
        tmp_path / "ws",
        {
            "test_net.py": """\
            import socket

            import pytest


            def test_no_route_out():
                with pytest.raises(OSError):
                    socket.create_connection(("1.1.1.1", 80), timeout=3)


            def test_no_dns():
                with pytest.raises(OSError):
                    socket.getaddrinfo("example.com", 80)
            """
        },
    )
    result = _run(image, ws)
    assert result.outcome is RunOutcome.PASSED, result.log_tail
    assert len(result.tests) == 2


def test_hardening(image: BuildResult, tmp_path: Path) -> None:
    ws = _workspace(
        tmp_path / "ws",
        {
            "test_hardening.py": """\
            import errno
            import os
            from pathlib import Path

            import pytest


            def test_runs_as_1000():
                assert os.getuid() == 1000
                assert os.getgid() == 1000


            def test_rootfs_read_only():
                mounts = [line.split() for line in Path("/proc/mounts").read_text().splitlines()]
                root_options = [m[3].split(",") for m in mounts if m[1] == "/"]
                assert root_options, mounts
                assert "ro" in root_options[-1]
                assert Path("/owned").stat().st_uid == 1000
                with pytest.raises(OSError) as info:
                    Path("/owned/x").write_text("x")
                assert info.value.errno == errno.EROFS


            def test_workspace_tmp_results_writable():
                Path("/workspace/new.txt").write_text("ok")
                Path("/tmp/new.txt").write_text("ok")
                Path(os.environ["PG_RESULTS"], "extra.txt").write_text("ok")
                assert Path("/workspace").stat().st_uid == 1000
                assert Path("/workspace/test_hardening.py").stat().st_uid == 1000


            def test_no_capabilities():
                status = Path("/proc/self/status").read_text()
                eff = next(line for line in status.splitlines() if line.startswith("CapEff"))
                assert int(eff.split()[1], 16) == 0
                assert "NoNewPrivs:\\t1" in status
            """
        },
    )
    result = _run(image, ws)
    assert result.outcome is RunOutcome.PASSED, result.log_tail
    assert len(result.tests) == 4


def test_interrupt_tears_down(
    image: BuildResult, tmp_path: Path, engine: docker.DockerClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(container: Container, limits: Limits) -> RunResult:
        raise KeyboardInterrupt

    monkeypatch.setattr(sandbox_run, "_wait_and_collect", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _run(image, _workspace(tmp_path / "ws", {}), "sleep 120")
    _assert_no_leftovers(engine)


def test_unknown_image(tmp_path: Path, engine: docker.DockerClient) -> None:
    with pytest.raises(SandboxError, match="image not found"):
        run_check("sha256:" + "0" * 64, [_workspace(tmp_path / "ws", {})], "true")
    _assert_no_leftovers(engine)


def test_no_leftovers_after_all_runs(engine: docker.DockerClient) -> None:
    _assert_no_leftovers(engine)
