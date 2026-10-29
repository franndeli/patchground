"""Build phase: build a challenge image from its environment directory.

The build has network access (dependencies install here, never at run time). Consent for untrusted
sources is the caller's job and must happen before :func:`build_image` is called.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker.errors
import requests
import urllib3.exceptions

from patchground.sandbox._engine import connect
from patchground.sandbox.errors import BuildFailed, SandboxError

#: Limits applied to every intermediate build container.
BUILD_MEMORY_BYTES = 4 * 1024**3

#: Default wall-clock budget for one image build.
DEFAULT_BUILD_TIMEOUT_SECONDS = 1800.0
#: A connection error this close to the deadline counts as the deadline being hit.
TIMEOUT_TOLERANCE_SECONDS = 1.0

_NAME_RE = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
_BUILT_RE = re.compile(r"^Successfully built ([0-9a-f]+)$")


@dataclass(frozen=True)
class BuildResult:
    """A built image: ``image_id`` is the engine's opaque id, ``tag`` the cache tag."""

    image_id: str
    tag: str
    log: str


def context_hash(context: Path) -> str:
    """Return a deterministic sha256 hex digest of a build context directory.

    Covers every entry's relative path, kind, permission bits and content (symlinks by their
    target text), in sorted path order, so the same tree always yields the same hash.
    """
    entries: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(context):
        dirnames.sort()
        base = Path(dirpath)
        for name in [*dirnames, *filenames]:
            path = base / name
            entries.append((path.relative_to(context).as_posix(), path))
    digest = hashlib.sha256()
    for rel, path in sorted(entries):
        st = path.lstat()
        mode = stat.S_IMODE(st.st_mode)
        digest.update(rel.encode("utf-8", "surrogateescape") + b"\0")
        if stat.S_ISLNK(st.st_mode):
            digest.update(b"L\0" + str(path.readlink()).encode("utf-8", "surrogateescape"))
        elif stat.S_ISDIR(st.st_mode):
            digest.update(b"D\0" + f"{mode:o}".encode())
        elif stat.S_ISREG(st.st_mode):
            content = path.read_bytes()
            digest.update(b"F\0" + f"{mode:o}\0{len(content)}\0".encode() + content)
        else:
            digest.update(b"O\0")
        digest.update(b"\0")
    return digest.hexdigest()


def _log_text(chunks: Any) -> str:
    parts: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            parts.append(f"{chunk}\n")
            continue
        for key in ("stream", "error"):
            value = chunk.get(key)
            if isinstance(value, str):
                parts.append(value if key == "stream" else f"{value}\n")
    return "".join(parts)


def _note(log: str, note: str) -> str:
    if log and not log.endswith("\n"):
        log += "\n"
    return f"{log}[patchground] {note}\n"


def build_image(
    dockerfile: Path, *, name: str, timeout_seconds: float = DEFAULT_BUILD_TIMEOUT_SECONDS
) -> BuildResult:
    """Build ``dockerfile`` with its parent directory as the context.

    The image is tagged ``patchground/<name>:<hash12>`` where ``hash12`` is the start of
    :func:`context_hash` over the context directory.

    Uses the Docker Engine API's classic (legacy, non-BuildKit) builder, which is what the
    Docker SDK drives. No host mounts and no engine socket are exposed to the build; each build
    container is capped at :data:`BUILD_MEMORY_BYTES` without swap.

    ``timeout_seconds`` is the build's wall-clock budget. It is checked every time the builder
    emits output, and the HTTP read timeout of the build request is set to the same value, so a
    silent step (e.g. ``RUN sleep``) aborts the build once it has been quiet that long; a build
    that goes quiet just before the deadline can therefore overrun it by up to one more
    ``timeout_seconds``. Aborting closes the build connection, which makes the engine cancel the
    build and remove its intermediate container.

    Raises :class:`BuildFailed` (with the build log) if the build fails or exceeds
    ``timeout_seconds``, :class:`EngineUnavailable` if the engine cannot be reached,
    :class:`SandboxError` for engine-side failures (5xx, lost connection), and
    :class:`ValueError` for an invalid ``name``, path or timeout.
    """
    if not _NAME_RE.fullmatch(name):
        raise ValueError(
            f"invalid image name {name!r}: use lowercase letters, digits, '.', '_', '-'"
        )
    if timeout_seconds <= 0:
        raise ValueError(f"timeout_seconds must be positive: {timeout_seconds}")
    if not dockerfile.is_file():
        raise ValueError(f"Dockerfile not found: {dockerfile}")
    context = dockerfile.parent.resolve()
    tag = f"patchground/{name}:{context_hash(context)[:12]}"
    exceeded = f"image build exceeded {timeout_seconds:g} s"
    chunks: list[Any] = []
    client = connect()
    started = time.monotonic()
    try:
        stream = client.api.build(
            path=str(context),
            dockerfile=dockerfile.name,
            tag=tag,
            rm=True,
            forcerm=True,
            pull=False,
            container_limits={"memory": BUILD_MEMORY_BYTES, "memswap": BUILD_MEMORY_BYTES},
            labels={"patchground": "1"},
            decode=True,
            timeout=math.ceil(timeout_seconds),
        )
        image_id: str | None = None
        for chunk in stream:
            chunks.append(chunk)
            if time.monotonic() - started > timeout_seconds:
                raise BuildFailed(_note(_log_text(chunks), exceeded), message=exceeded)
            if not isinstance(chunk, dict):
                continue
            if "error" in chunk:
                raise BuildFailed(_log_text(chunks))
            image_id = _image_id(chunk) or image_id
        log = _log_text(chunks)
        if image_id is None:
            raise BuildFailed(_note(log, "the builder reported no image id"))
        image = client.images.get(image_id)
    except (
        requests.exceptions.ReadTimeout,
        requests.exceptions.ConnectionError,
        urllib3.exceptions.ReadTimeoutError,
        urllib3.exceptions.ProtocolError,
    ) as exc:
        # A silent build step outlasting the read timeout surfaces as ReadTimeout/ConnectionError
        # (docker/docker-py#1966) or, while the log streams, as urllib3's ReadTimeoutError.
        # Well before the deadline it is a lost engine instead.
        if time.monotonic() - started >= timeout_seconds - TIMEOUT_TOLERANCE_SECONDS:
            raise BuildFailed(_note(_log_text(chunks), exceeded), message=exceeded) from exc
        raise SandboxError(f"engine connection lost during build: {exc}") from exc
    except docker.errors.APIError as exc:
        status = exc.status_code
        if status is not None and 400 <= status < 500:
            raise BuildFailed(_note(_log_text(chunks), str(exc))) from exc
        raise SandboxError(f"image build did not complete: {exc}") from exc
    except (
        docker.errors.DockerException,
        requests.exceptions.RequestException,
        urllib3.exceptions.HTTPError,
    ) as exc:
        raise SandboxError(f"image build did not complete: {exc}") from exc
    finally:
        client.close()
    if image.id is None:
        raise SandboxError("engine returned an image without an id")
    return BuildResult(image_id=image.id, tag=tag, log=log)


def _image_id(chunk: dict[str, Any]) -> str | None:
    """The image id announced by a build chunk (``aux.ID`` or "Successfully built <id>")."""
    aux = chunk.get("aux")
    if isinstance(aux, dict) and isinstance(aux.get("ID"), str):
        return str(aux["ID"])
    stream = chunk.get("stream")
    if isinstance(stream, str):
        match = _BUILT_RE.search(stream.strip())
        if match:
            return match.group(1)
    return None
