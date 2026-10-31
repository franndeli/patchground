"""Integration tests for the sandbox against a real container engine."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import closing
from itertools import islice
from pathlib import Path
from textwrap import dedent
from unittest.mock import Mock

import docker
import pytest
from docker.models.containers import Container

from patchground.sandbox import (
    BuildFailed,
    BuildResult,
    CommandResult,
    Limits,
    RunOutcome,
    RunResult,
    SandboxError,
    TestStatus,
    build_image,
    run_check,
    run_command,
)
from patchground.sandbox import run as sandbox_run
from patchground.sandbox.run import MAX_OUTPUT_TAIL_BYTES

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


# --------------------------------------------------------------------------- run_command


def _command(
    image: BuildResult, ws: Path, argv: list[str], limits: Limits | None = None
) -> CommandResult:
    return run_command(image.image_id, [ws], argv, limits=limits or Limits())


def test_command_exit_codes_and_combined_output(
    image: BuildResult, tmp_path: Path, engine: docker.DockerClient
) -> None:
    ws = _workspace(tmp_path / "ws", {"visible.txt": "seen\n"})
    ok = _command(image, ws, ["sh", "-c", "cat visible.txt; echo err >&2"])
    assert (ok.exit_code, ok.limit, ok.output_tail_only) == (0, None, True)
    assert sorted(ok.output_tail.splitlines()) == ["err", "seen"]
    bad = _command(image, ws, ["sh", "-c", "echo out; exit 7"])
    assert (bad.exit_code, bad.output_tail) == (7, "out\n")
    _assert_no_leftovers(engine)


def test_command_argv_is_literal(image: BuildResult, tmp_path: Path) -> None:
    ws = _workspace(tmp_path / "ws", {})
    argv = ["python", "-c", "import sys; print(sys.argv[1:])", "$HOME; `id` $(id) *", "a b"]
    result = _command(image, ws, argv)
    assert result.output_tail.strip() == "['$HOME; `id` $(id) *', 'a b']"
    assert not (tmp_path / "ws" / "a").exists()


def test_command_has_no_host_environment(
    image: BuildResult, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PG_FAKE_SECRET", "sk-test-not-a-real-key")
    result = _command(image, _workspace(tmp_path / "ws", {}), ["env"])
    assert "sk-test-not-a-real-key" not in result.output_tail
    assert "PG_FAKE_SECRET" not in result.output_tail


def test_command_sees_only_given_layers_and_edits_are_discarded(
    image: BuildResult, tmp_path: Path
) -> None:
    ws = _workspace(tmp_path / "ws", {"keep.txt": "original\n"})
    result = _command(image, ws, ["sh", "-c", "ls; echo changed > keep.txt; rm -f keep.txt"])
    assert result.output_tail.split() == ["keep.txt"]
    assert (ws / "keep.txt").read_text() == "original\n"


def test_command_hardening(image: BuildResult, tmp_path: Path) -> None:
    script = (
        "import os, socket\n"
        "print(os.getuid(), os.getgid())\n"
        "for p in ('/owned/x', '/usr/x'):\n"
        "    try: open(p, 'w')\n"
        "    except OSError as e: print('ro', p, e.errno)\n"
        "open('/workspace/w', 'w'); open('/tmp/t', 'w')\n"
        "try: socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
        "except OSError: print('no-net')\n"
        "print(open('/proc/self/status').read().split('CapEff:')[1].split()[0])\n"
    )
    out = _command(image, _workspace(tmp_path / "ws", {}), ["python", "-c", script]).output_tail
    assert out.splitlines() == [
        "1000 1000",
        "ro /owned/x 30",
        "ro /usr/x 30",
        "no-net",
        "0000000000000000",
    ]


def test_command_output_is_bounded_and_sanitized(
    image: BuildResult, tmp_path: Path, engine: docker.DockerClient
) -> None:
    script = (
        "import sys\n"
        "sys.stdout.write('first-line-dropped\\n' + 'x' * 5_000_000 + '\\n')\n"
        "sys.stdout.write('\\x1b[31mred\\x1b[0m\\x1b]0;title\\x07 tail-marker\\n')\n"
    )
    result = _command(image, _workspace(tmp_path / "ws", {}), ["python", "-c", script])
    assert result.exit_code == 0
    assert len(result.output_tail.encode()) <= MAX_OUTPUT_TAIL_BYTES
    assert result.output_tail.endswith("red tail-marker\n")
    assert "first-line-dropped" not in result.output_tail and "\x1b" not in result.output_tail
    _assert_no_leftovers(engine)


def test_command_engine_log_is_bounded(
    image: BuildResult, tmp_path: Path, engine: docker.DockerClient
) -> None:
    ws = _workspace(tmp_path / "ws", {})
    script = "import sys\nfor i in range(200):\n    sys.stdout.write('y' * 99_999 + '\\n')\n"
    seen: list[Container] = []
    original = sandbox_run._output_tail

    def spy(container: Container) -> str:
        seen.append(container)
        assert container.attrs["HostConfig"]["LogConfig"] == sandbox_run.LOG_CONFIG
        return original(container)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sandbox_run, "_output_tail", spy)
        result = _command(image, ws, ["python", "-c", script])
    assert seen and len(result.output_tail.encode()) <= MAX_OUTPUT_TAIL_BYTES
    assert result.output_tail.endswith("y\n")


def _oom_diagnostics(
    container: Container, engine: docker.DockerClient, *, since: int
) -> dict[str, object]:
    evidence: dict[str, object] = {}
    samples = []
    evidence["state_samples_100ms"] = samples
    try:
        for attempt in range(11):
            if attempt:
                time.sleep(0.1)
                container.reload()
            state = container.attrs["State"]
            samples.append({key: state.get(key) for key in ("Running", "ExitCode", "OOMKilled")})
            if state.get("OOMKilled"):
                break
    except Exception:
        evidence["state_unavailable"] = True
    if samples and samples[0]["OOMKilled"]:
        return evidence
    try:
        evidence["engine_version"] = engine.version().get("Version")
    except Exception:
        evidence["engine_version_unavailable"] = True
    try:
        # CancellableStream has close(), but does not implement the context-manager protocol.
        with closing(
            engine.events(
                since=since,
                until=int(time.time()) + 1,
                filters={"container": container.id, "event": ["oom", "die", "kill"]},
                decode=True,
            )
        ) as events:
            evidence["events"] = [
                (event.get("Action"), event.get("timeNano")) for event in islice(events, 16)
            ]
    except Exception:
        # Diagnostics must never replace the original assertion or expose engine error text.
        evidence["events_unavailable"] = True
    return evidence


def test_command_timeout_and_memory_limits(
    image: BuildResult,
    tmp_path: Path,
    engine: docker.DockerClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = _workspace(tmp_path / "ws", {})
    slow = _command(image, ws, ["sh", "-c", "echo started; sleep 60"], Limits(timeout_seconds=3))
    assert (slow.exit_code, slow.limit, slow.output_tail) == (None, "timeout", "started\n")
    # Keep failure evidence before teardown: distinguish a late OOM event from an engine
    # that never confirms OOM. This never changes the result being asserted below.
    evidence: dict[str, object] = {}
    output_tail = sandbox_run._output_tail
    since = int(time.time()) - 1

    def capture(container: Container) -> str:
        evidence.update(_oom_diagnostics(container, engine, since=since))
        return output_tail(container)

    monkeypatch.setattr(sandbox_run, "_output_tail", capture)
    hog = _command(
        image,
        ws,
        ["python", "-c", "b = bytearray(); [b.extend(bytes(10**7)) for _ in range(100)]"],
        Limits(memory_bytes=128 * 1024**2),
    )
    assert hog.limit == "memory", evidence
    _assert_no_leftovers(engine)


@pytest.mark.parametrize("delayed", [False, True], ids=["absent", "delayed"])
def test_oom_diagnostics_collect_and_close(monkeypatch: pytest.MonkeyPatch, delayed: bool) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)
    container = Mock(attrs={"State": {"Running": False, "ExitCode": 137, "OOMKilled": False}})
    if delayed:
        container.reload.side_effect = lambda: container.attrs["State"].update(OOMKilled=True)
    # Like docker.types.CancellableStream, this iterator supports close but no __enter__.
    events = Mock(spec=["__iter__", "close"])
    events.__iter__ = Mock(return_value=iter([{"Action": "oom", "timeNano": 123}]))
    engine = Mock()
    engine.events.return_value = events
    engine.version.return_value = {"Version": "28.5.2"}
    evidence = _oom_diagnostics(container, engine, since=1)
    samples = evidence["state_samples_100ms"]
    assert len(samples) == (2 if delayed else 11)
    assert samples[0]["OOMKilled"] is False
    assert samples[-1]["OOMKilled"] is delayed
    assert evidence["events"] == [("oom", 123)]
    events.close.assert_called_once()


@pytest.mark.parametrize("failure", ["reload", "version", "events", "iteration", "close"])
def test_oom_diagnostics_failures_are_safe(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)
    container = Mock(attrs={"State": {"OOMKilled": False}})
    engine = Mock()
    engine.version.return_value = {"Version": "28.5.2"}
    events = Mock(spec=["__iter__", "close"])
    events.__iter__ = Mock(return_value=iter([]))
    engine.events.return_value = events
    target = {
        "reload": container.reload,
        "version": engine.version,
        "events": engine.events,
        "iteration": events.__iter__,
        "close": events.close,
    }[failure]
    target.side_effect = RuntimeError("private engine error must not appear")
    evidence = _oom_diagnostics(container, engine, since=1)
    assert "unavailable" in repr(evidence)
    assert "private" not in repr(evidence)
    if failure in ("iteration", "close"):
        events.close.assert_called_once()


def test_oom_diagnostics_cap_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)
    container = Mock(attrs={"State": {"OOMKilled": False}})
    events = Mock(spec=["__iter__", "close"])
    events.__iter__ = Mock(
        return_value=({"Action": "oom", "timeNano": i} for i in range(1_000_000))
    )
    engine = Mock()
    engine.events.return_value = events
    engine.version.return_value = {"Version": "28.5.2"}
    evidence = _oom_diagnostics(container, engine, since=1)
    assert len(evidence["events"]) == 16
    events.close.assert_called_once()


@pytest.mark.parametrize("delayed", [False, True], ids=["absent", "delayed"])
def test_oom_diagnostics_preserve_memory_assertion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, delayed: bool
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(sandbox_run, "_output_tail", lambda _: "")
    container = Mock(attrs={"State": {"OOMKilled": False}})
    if delayed:
        container.reload.side_effect = lambda: container.attrs["State"].update(OOMKilled=True)
    engine = Mock()
    engine.version.return_value = {"Version": "28.5.2"}
    engine.events.side_effect = RuntimeError("private engine error must not appear")

    def command(_image: object, _ws: Path, argv: list[str], _limits: Limits) -> CommandResult:
        if argv[0] == "sh":
            return CommandResult(None, "timeout", "started\n")
        sandbox_run._output_tail(container)
        # The already classified result must not be changed by delayed diagnostic evidence.
        return CommandResult(137, None, "")

    monkeypatch.setattr(f"{__name__}._command", command)
    with pytest.raises(AssertionError) as error:
        test_command_timeout_and_memory_limits(Mock(), tmp_path, engine, monkeypatch)
    assert "events_unavailable" in str(error.value)
    assert "private" not in str(error.value)


def test_command_sigkill_is_not_a_memory_limit(
    image: BuildResult,
    tmp_path: Path,
    engine: docker.DockerClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wait = sandbox_run._wait

    def kill_and_wait(container: Container, limits: Limits) -> int | None:
        # PID 1 can ignore a self-sent signal; send SIGKILL through the engine instead.
        container.kill()
        return wait(container, limits)

    monkeypatch.setattr(sandbox_run, "_wait", kill_and_wait)
    result = _command(
        image,
        _workspace(tmp_path / "ws", {}),
        ["sleep", "60"],
    )
    assert (result.exit_code, result.limit) == (137, None)
    _assert_no_leftovers(engine)


@pytest.mark.parametrize(("argv", "code"), [(["no-such-program"], 127), (["/workspace"], 126)])
def test_command_that_cannot_start(
    image: BuildResult, tmp_path: Path, engine: docker.DockerClient, argv: list[str], code: int
) -> None:
    result = _command(image, _workspace(tmp_path / "ws", {}), argv)
    assert (result.exit_code, result.limit, result.output_tail) == (code, None, "")
    _assert_no_leftovers(engine)


def test_command_interrupt_tears_down(
    image: BuildResult, tmp_path: Path, engine: docker.DockerClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(container: Container, limits: Limits) -> int | None:
        raise KeyboardInterrupt

    monkeypatch.setattr(sandbox_run, "_wait", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _command(image, _workspace(tmp_path / "ws", {}), ["sleep", "120"])
    _assert_no_leftovers(engine)


def test_command_unknown_image(tmp_path: Path, engine: docker.DockerClient) -> None:
    with pytest.raises(SandboxError, match="image not found"):
        run_command("sha256:" + "0" * 64, [_workspace(tmp_path / "ws", {})], ["true"])
    _assert_no_leftovers(engine)


def test_empty_workspace_is_writable_by_the_run_user(image: BuildResult, tmp_path: Path) -> None:
    ws = tmp_path / "empty"
    ws.mkdir()
    script = (
        "import os\n"
        "print(os.getuid(), os.stat('/workspace').st_uid, os.stat('/results').st_uid)\n"
        "print(os.listdir('/workspace'))\n"
        "open('/workspace/w', 'w').close()\n"
        "open('/results/r', 'w').close()\n"
        "try: open('/usr/x', 'w')\n"
        "except OSError as e: print('ro', e.errno)\n"
    )
    result = _command(image, ws, ["python", "-c", script])
    assert result.exit_code == 0, result.output_tail
    assert result.output_tail.splitlines() == ["1000 1000 1000", "[]", "ro 30"]
    check = _run(image, ws, "touch /workspace/w /results/r")
    assert check.exit_code == 0 and check.outcome is RunOutcome.MISSING_RESULTS
