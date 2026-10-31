"""Run phase: execute a command against a copy of some files inside a hardened container.

Every run gets a fresh container on a fresh ``internal`` bridge network (no route out), a
read-only root filesystem, and two fresh volumes, ``/workspace`` and ``/results``, which are the
only writable paths besides a small ``/tmp`` tmpfs. Files are copied into the volumes with
``put_archive`` through a never-started "seed" container before the run container is created
(see :func:`_create_seed`). Results come from ``/results/junit.xml`` only; the exit code is
informative. Containers, volumes and network are removed in a ``finally``, also on timeout,
errors and ``KeyboardInterrupt``.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import stat
import tarfile
import time
import uuid
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import docker.errors
import requests
import urllib3.exceptions
from docker import DockerClient
from docker.models.containers import Container
from docker.models.networks import Network
from docker.models.volumes import Volume
from docker.types import LogConfig, Mount

from patchground.sandbox._engine import connect
from patchground.sandbox.errors import JUnitError, SandboxError
from patchground.sandbox.junit import TestResult, TestStatus, parse_junit

RUN_UID = 1000
RUN_GID = 1000
WORKSPACE = "/workspace"
RESULTS = "/results"
JUNIT_PATH = f"{RESULTS}/junit.xml"
#: Largest junit.xml accepted from a container.
MAX_JUNIT_BYTES = 50 * 1024**2
LOG_TAIL_LINES = 200
#: Most bytes of sanitized combined output ``run_command`` returns (the tail of the output).
MAX_OUTPUT_TAIL_BYTES = 64 * 1024
#: Raw log bytes kept while streaming; sanitizing only shrinks them, so the tail still fills.
_RAW_TAIL_BYTES = 4 * MAX_OUTPUT_TAIL_BYTES
#: The engine keeps at most ``max-size * max-file`` of a container's output, whatever it prints.
LOG_CONFIG = LogConfig(type="json-file", config={"max-size": "1m", "max-file": "2"})
#: Exit codes the OCI runtime uses for "found but not executable" / "not found".
_EXEC_FAILURE_CODES = (126, 127)
#: A connection error this close to the wall-clock limit counts as the limit being hit.
TIMEOUT_TOLERANCE_SECONDS = 1.0
LABELS = {"patchground": "1"}


@dataclass(frozen=True)
class Limits:
    """Per-run resource limits (defaults from ``patchground-contract-execution``)."""

    cpus: float = 2.0
    memory_bytes: int = 2 * 1024**3
    pids: int = 512
    timeout_seconds: float = 600.0

    def __post_init__(self) -> None:
        if self.cpus <= 0 or self.memory_bytes <= 0 or self.pids <= 0 or self.timeout_seconds <= 0:
            raise ValueError(f"limits must be positive: {self}")


DEFAULT_LIMITS = Limits()


class RunOutcome(StrEnum):
    """Overall outcome of a run, derived from JUnit results (never from the exit code)."""

    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"
    MISSING_RESULTS = "missing_results"
    LIMIT_EXCEEDED = "limit_exceeded"


@dataclass(frozen=True)
class RunResult:
    """Result of :func:`run_check`.

    ``limit`` is ``"timeout"`` or ``"memory"`` when ``outcome`` is ``LIMIT_EXCEEDED``.
    ``log_tail`` is the last ~200 lines of combined stdout/stderr, followed by any
    ``[patchground]`` notes explaining the outcome.

    ``log_tail`` is raw test-runner output and may contain test sources (assertion rewrites,
    tracebacks), including those of hidden checks. Callers must not display it for runs that
    included hidden layers. Prefixed note lines are also untrusted; tests can spoof them.
    """

    outcome: RunOutcome
    tests: tuple[TestResult, ...]
    exit_code: int | None
    limit: str | None
    log_tail: str


@dataclass(frozen=True)
class CommandResult:
    """Result of :func:`run_command`.

    ``output_tail`` is the sanitized tail (at most :data:`MAX_OUTPUT_TAIL_BYTES` bytes of UTF-8)
    of the combined stdout/stderr of the command; earlier output may have been dropped, which
    ``output_tail_only`` (always true) states. It is arbitrary command output: untrusted text with
    terminal control sequences removed, never engine error text. ``limit`` is ``"timeout"`` or
    ``"memory"`` when a resource limit ended the run; ``exit_code`` is ``None`` on timeout.
    """

    exit_code: int | None
    limit: str | None
    output_tail: str
    output_tail_only: bool = True


# --------------------------------------------------------------------------- tar building


def _tarinfo(name: str, mode: int, mtime: float, *, size: int = 0, is_dir: bool) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if is_dir else tarfile.REGTYPE
    info.mode = mode
    info.size = size
    info.mtime = int(mtime)
    info.uid = RUN_UID
    info.gid = RUN_GID
    info.uname = ""
    info.gname = ""
    return info


def _collect(layer: Path) -> dict[str, tuple[Path, bool]]:
    """Map relative POSIX path -> (path, is_dir) for one layer; reject non-regular files."""
    if not layer.is_dir() or layer.is_symlink():
        raise SandboxError(f"layer is not a directory: {layer}")
    entries: dict[str, tuple[Path, bool]] = {}
    for dirpath, dirnames, filenames in os.walk(layer):
        base = Path(dirpath)
        for name in [*dirnames, *filenames]:
            path = base / name
            st = path.lstat()
            rel = path.relative_to(layer).as_posix()
            if stat.S_ISDIR(st.st_mode):
                entries[rel] = (path, True)
            elif stat.S_ISREG(st.st_mode):
                entries[rel] = (path, False)
            else:
                kind = "symlink" if stat.S_ISLNK(st.st_mode) else "special file"
                raise SandboxError(f"refusing to copy {kind} into the sandbox: {path}")
    return entries


def build_seed_tar(layers: Sequence[Path]) -> bytes:
    """Build the in-memory tar that seeds the ``workspace`` and ``results`` volumes.

    It is extracted at ``/`` of the seed container, so it holds a ``workspace/`` directory with
    ``layers`` (directories, applied in order) and an empty ``results/`` directory. Every entry is
    owned by uid/gid 1000 and keeps its permission bits (setuid/setgid/sticky stripped); the two
    top-level entries make the volume roots themselves owned by 1000 and mode 0755.

    Directories may appear in several layers; any other path clash between layers is a caller
    bug and raises :class:`SandboxError`, as do symlinks and special files anywhere in a layer
    and files that cannot be read.
    """
    try:
        return _build_seed_tar(layers)
    except OSError as exc:
        raise SandboxError(f"cannot read files to copy into the sandbox: {exc}") from exc


def _build_seed_tar(layers: Sequence[Path]) -> bytes:
    merged: dict[str, tuple[Path, bool]] = {}
    for layer in layers:
        for rel, (path, is_dir) in _collect(layer).items():
            previous = merged.get(rel)
            if previous is not None and not (previous[1] and is_dir):
                raise SandboxError(f"path {rel!r} is provided by more than one layer")
            merged.setdefault(rel, (path, is_dir))
    now = time.time()
    ws = WORKSPACE.lstrip("/")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        tar.addfile(_tarinfo(f"{ws}/", 0o755, now, is_dir=True))
        for rel in sorted(merged):
            path, is_dir = merged[rel]
            st = path.stat()
            mode = stat.S_IMODE(st.st_mode) & 0o777
            if is_dir:
                tar.addfile(_tarinfo(f"{ws}/{rel}/", mode, st.st_mtime, is_dir=True))
            else:
                with path.open("rb") as fh:
                    info = _tarinfo(f"{ws}/{rel}", mode, st.st_mtime, size=st.st_size, is_dir=False)
                    tar.addfile(info, fh)
        tar.addfile(_tarinfo(f"{RESULTS.lstrip('/')}/", 0o755, now, is_dir=True))
    return buf.getvalue()


def _extract_single_file(chunks: Iterable[bytes], limit: int) -> bytes:
    """Return the bytes of the one regular file in a ``get_archive`` tar stream."""
    buf = io.BytesIO()
    for chunk in chunks:
        buf.write(chunk)
        if buf.tell() > limit + 64 * 1024:  # file plus tar headers/padding
            raise JUnitError(f"junit.xml is larger than {limit} bytes")
    buf.seek(0)
    try:
        with tarfile.open(fileobj=buf, mode="r:") as tar:
            members = tar.getmembers()
            if len(members) != 1 or not members[0].isreg():
                raise JUnitError("junit.xml is not a regular file")
            if members[0].size > limit:
                raise JUnitError(f"junit.xml is larger than {limit} bytes")
            fh = tar.extractfile(members[0])
            if fh is None:
                raise JUnitError("junit.xml could not be read")
            return fh.read()
    except tarfile.TarError as exc:
        raise JUnitError(f"could not read junit.xml archive: {exc}") from exc


# --------------------------------------------------------------------------- outcome rules


def outcome_for(tests: Sequence[TestResult]) -> tuple[RunOutcome, str | None]:
    """Derive the run outcome from parsed tests; returns (outcome, explanatory note or None)."""
    if not tests:
        return RunOutcome.ERRORED, "junit.xml contains no test cases"
    statuses = {t.status for t in tests}
    if TestStatus.ERRORED in statuses:
        return RunOutcome.ERRORED, None
    if TestStatus.FAILED in statuses:
        return RunOutcome.FAILED, None
    return RunOutcome.PASSED, None


def _with_notes(log: str, notes: Sequence[str]) -> str:
    if not notes:
        return log
    suffix = "\n".join(f"[patchground] {note}" for note in notes)
    if log and not log.endswith("\n"):
        log += "\n"
    return log + suffix + "\n"


# --------------------------------------------------------------------------- run


@contextlib.contextmanager
def _hardened_container(
    image_id: str,
    layers: Sequence[Path],
    *,
    entrypoint: list[str],
    command: list[str],
    limits: Limits,
) -> Iterator[Container]:
    """Yield a created, not yet started hardened container seeded with a copy of ``layers``.

    This is the single run lifecycle of the module: fresh internal network and volumes, seed
    archive, the hardened container, and teardown of all of it on every exit path, including
    errors and ``KeyboardInterrupt``. Engine failures become :class:`SandboxError`.
    """
    seed_tar = build_seed_tar(layers)
    run_id = f"patchground-{uuid.uuid4().hex}"
    client = connect()
    network: Network | None = None
    volumes: list[Volume] = []
    seed: Container | None = None
    container: Container | None = None
    try:
        network = client.networks.create(run_id, driver="bridge", internal=True, labels=LABELS)
        for suffix in ("workspace", "results"):
            volumes.append(client.volumes.create(name=f"{run_id}-{suffix}", labels=LABELS))
        mounts = [
            Mount(WORKSPACE, _name(volumes[0]), type="volume", no_copy=True),
            Mount(RESULTS, _name(volumes[1]), type="volume", no_copy=True),
        ]
        seed = _create_seed(client, image_id, mounts)
        if not seed.put_archive("/", seed_tar):
            raise SandboxError("could not copy files into the sandbox")
        _remove_container(seed)
        seed = None
        container = _create_container(
            client, image_id, entrypoint, command, mounts, _name(network), limits
        )
        yield container
    except (
        docker.errors.DockerException,
        requests.exceptions.RequestException,
        urllib3.exceptions.HTTPError,
    ) as exc:
        raise SandboxError(f"sandbox run failed: {exc}") from exc
    finally:
        _teardown([c for c in (seed, container) if c is not None], volumes, network)
        client.close()


def run_check(
    image_id: str,
    layers: Sequence[Path],
    command: str,
    *,
    limits: Limits = DEFAULT_LIMITS,
) -> RunResult:
    """Run ``command`` (via ``/bin/sh -c``) in ``image_id`` against a copy of ``layers``.

    ``layers`` are directories merged into ``/workspace`` in order (see :func:`build_seed_tar`).
    The command runs as uid/gid 1000 with ``PG_RESULTS=/results`` and must write
    ``/results/junit.xml``. The image's ENTRYPOINT is overridden.

    Raises :class:`EngineUnavailable` if the engine is unreachable and :class:`SandboxError`
    for invalid layers or engine failures; test outcomes are reported in the result.
    """
    with _hardened_container(
        image_id, layers, entrypoint=["/bin/sh", "-c"], command=[command], limits=limits
    ) as container:
        container.start()
        return _wait_and_collect(container, limits)


def run_command(
    image_id: str,
    layers: Sequence[Path],
    argv: Sequence[str],
    *,
    limits: Limits = DEFAULT_LIMITS,
) -> CommandResult:
    """Run ``argv`` literally (no shell unless ``argv`` names one) against a copy of ``layers``.

    Same container, hardening, limits and teardown as :func:`run_check`; the image's ENTRYPOINT is
    replaced by ``argv[0]``. Nothing from the host environment is passed in, and no JUnit is read.
    A command that cannot be started (missing or non-executable program) reports exit code 126 or
    127 with empty output. Raises :class:`SandboxError` for an empty or NUL-containing ``argv``,
    invalid layers or engine failures.
    """
    if not argv or not argv[0]:
        raise SandboxError("command is empty")
    if any("\0" in arg for arg in argv):
        raise SandboxError("command arguments cannot contain NUL bytes")
    with _hardened_container(
        image_id, layers, entrypoint=[argv[0]], command=list(argv[1:]), limits=limits
    ) as container:
        try:
            container.start()
        except docker.errors.APIError:
            # An unrunnable program is the command's outcome, not an infrastructure failure;
            # the engine's message is deliberately dropped.
            container.reload()
            state = container.attrs.get("State", {})
            code = state.get("ExitCode")
            if code not in _EXEC_FAILURE_CODES or state.get("Running"):
                raise
            return CommandResult(code, None, "")
        exit_code = _wait(container, limits)
        container.reload()
        oom_killed = bool(container.attrs.get("State", {}).get("OOMKilled", False))
        output = _output_tail(container)
    if exit_code is None:
        return CommandResult(None, "timeout", output)
    return CommandResult(exit_code, "memory" if oom_killed else None, output)


_ANSI = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?"  # OSC (titles, hyperlinks), also unterminated
    r"|\x1b[PX^_][^\x1b]*(?:\x1b\\)?"  # DCS / SOS / PM / APC strings
    r"|\x1b\[[0-?]*[ -/]*[@-~]"  # CSI
    r"|\x1b[ -/]*[0-~]?"  # other escapes, or a lone/truncated ESC
)
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def sanitize_output(raw: bytes) -> str:
    """Decode command output and drop terminal control sequences, keeping ``\\n`` and ``\\t``.

    Carriage returns are removed (``\\r\\n`` becomes ``\\n``), so output cannot overwrite what
    precedes it on a terminal line. The result is at most :data:`MAX_OUTPUT_TAIL_BYTES` bytes of
    UTF-8, keeping the end of the output.
    """
    text = raw.decode("utf-8", errors="replace")
    text = _CONTROLS.sub("", _ANSI.sub("", text))
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_OUTPUT_TAIL_BYTES:
        return text
    return encoded[-MAX_OUTPUT_TAIL_BYTES:].decode("utf-8", errors="ignore")


def _output_tail(container: Container) -> str:
    """Stream the container's (engine-bounded) log, keeping only a rolling raw tail in memory."""
    raw = bytearray()
    for chunk in container.logs(stdout=True, stderr=True, stream=True, follow=False):
        raw += chunk
        if len(raw) > 2 * _RAW_TAIL_BYTES:
            del raw[:-_RAW_TAIL_BYTES]
    return sanitize_output(bytes(raw[-_RAW_TAIL_BYTES:]))


def _name(resource: Network | Volume) -> str:
    name = resource.name
    if name is None:
        raise SandboxError("engine returned a resource without a name")
    return name


def _create_seed(client: DockerClient, image_id: str, mounts: list[Mount]) -> Container:
    """Create (never start) a container whose only job is to receive the seed archive.

    The engine ignores metadata of a tar's root entry (``.``) and refuses archives into a
    read-only rootfs, so the volume roots cannot be chowned through the run container. This
    writable, never-started container mounts the same volumes and takes the archive at ``/``,
    where ``workspace/`` and ``results/`` are ordinary entries whose ownership is applied.
    """
    try:
        return client.containers.create(
            image_id,
            ["true"],
            entrypoint=["/bin/true"],
            network_mode="none",
            mounts=mounts,
            labels=LABELS,
        )
    except docker.errors.ImageNotFound as exc:
        raise SandboxError(f"image not found: {image_id}") from exc


def _create_container(
    client: DockerClient,
    image_id: str,
    entrypoint: list[str],
    command: list[str],
    mounts: list[Mount],
    network_name: str,
    limits: Limits,
) -> Container:
    return client.containers.create(
        image_id,
        command,
        entrypoint=entrypoint,
        user=f"{RUN_UID}:{RUN_GID}",
        working_dir=WORKSPACE,
        environment={"PG_RESULTS": RESULTS, "HOME": "/tmp"},  # noqa: S108 - container path
        read_only=True,
        mounts=mounts,
        tmpfs={"/tmp": "rw,exec,size=256m,mode=1777"},  # noqa: S108 - container path
        network=network_name,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
        nano_cpus=int(limits.cpus * 1e9),
        mem_limit=limits.memory_bytes,
        memswap_limit=limits.memory_bytes,
        pids_limit=limits.pids,
        log_config=LOG_CONFIG,
        labels=LABELS,
    )


def _wait(container: Container, limits: Limits) -> int | None:
    """Wait for ``container`` to exit; its exit code, or ``None`` if it hit the wall clock.

    On timeout the container is killed. A connection error well before the deadline means the
    engine went away mid-run and raises :class:`SandboxError` (the caller still tears down).
    """
    started = time.monotonic()
    try:
        status = container.wait(timeout=limits.timeout_seconds)
    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as exc:
        # docker-py surfaces a wait() timeout as ReadTimeout or, depending on the transport,
        # as ConnectionError (docker/docker-py#1966); only near the deadline is it a timeout.
        elapsed = time.monotonic() - started
        if elapsed < limits.timeout_seconds - TIMEOUT_TOLERANCE_SECONDS:
            raise SandboxError(f"engine connection lost during run: {exc}") from exc
        with contextlib.suppress(docker.errors.DockerException):
            container.kill()
        return None
    return int(status["StatusCode"])


def _wait_and_collect(container: Container, limits: Limits) -> RunResult:
    exit_code = _wait(container, limits)
    timed_out = exit_code is None
    container.reload()
    oom_killed = bool(container.attrs.get("State", {}).get("OOMKilled", False))
    log = container.logs(stdout=True, stderr=True, tail=LOG_TAIL_LINES).decode(
        "utf-8", errors="replace"
    )

    if timed_out:
        note = f"wall-clock limit of {limits.timeout_seconds:g}s exceeded; container killed"
        return RunResult(RunOutcome.LIMIT_EXCEEDED, (), None, "timeout", _with_notes(log, [note]))
    if oom_killed:
        note = f"memory limit of {limits.memory_bytes} bytes exceeded (OOM killed)"
        return RunResult(
            RunOutcome.LIMIT_EXCEEDED, (), exit_code, "memory", _with_notes(log, [note])
        )

    try:
        chunks, _ = container.get_archive(JUNIT_PATH)
        tests = parse_junit(_extract_single_file(chunks, MAX_JUNIT_BYTES))
    except docker.errors.NotFound:
        note = f"{JUNIT_PATH} was not written by the test command"
        return RunResult(RunOutcome.MISSING_RESULTS, (), exit_code, None, _with_notes(log, [note]))
    except JUnitError as exc:
        note = f"{JUNIT_PATH} is unusable: {exc}"
        return RunResult(RunOutcome.MISSING_RESULTS, (), exit_code, None, _with_notes(log, [note]))

    outcome, explanation = outcome_for(tests)
    notes = [explanation] if explanation else []
    return RunResult(outcome, tests, exit_code, None, _with_notes(log, notes))


def _remove_container(container: Container) -> None:
    container.remove(v=True, force=True)


def _teardown(
    containers: Sequence[Container], volumes: Sequence[Volume], network: Network | None
) -> None:
    """Remove containers, then volumes, then the network; each step guarded, never raises."""
    for container in containers:
        with contextlib.suppress(Exception):
            _remove_container(container)
    for volume in volumes:
        with contextlib.suppress(Exception):
            volume.remove(force=True)
    if network is not None:
        with contextlib.suppress(Exception):
            network.remove()
