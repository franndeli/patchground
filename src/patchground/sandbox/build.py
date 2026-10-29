"""Build phase: build a challenge image from its environment directory.

The build has network access (dependencies install here, never at run time). Consent for untrusted
sources is the caller's job and must happen before :func:`build_image` is called.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker.errors
import requests

from patchground.sandbox._engine import connect
from patchground.sandbox.errors import BuildFailed, SandboxError

#: Limits applied to every intermediate build container.
BUILD_MEMORY_BYTES = 4 * 1024**3

_NAME_RE = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")


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


def build_image(dockerfile: Path, *, name: str) -> BuildResult:
    """Build ``dockerfile`` with its parent directory as the context.

    The image is tagged ``patchground/<name>:<hash12>`` where ``hash12`` is the start of
    :func:`context_hash` over the context directory.

    Uses the Docker Engine API's classic (legacy, non-BuildKit) builder, which is what the
    Docker SDK drives. No host mounts and no engine socket are exposed to the build; each build
    container is capped at :data:`BUILD_MEMORY_BYTES` without swap.

    Raises :class:`BuildFailed` (with the build log) if the build fails, :class:`EngineUnavailable`
    if the engine cannot be reached, and :class:`ValueError` for an invalid ``name`` or path.
    """
    if not _NAME_RE.fullmatch(name):
        raise ValueError(
            f"invalid image name {name!r}: use lowercase letters, digits, '.', '_', '-'"
        )
    if not dockerfile.is_file():
        raise ValueError(f"Dockerfile not found: {dockerfile}")
    context = dockerfile.parent.resolve()
    tag = f"patchground/{name}:{context_hash(context)[:12]}"
    client = connect()
    try:
        image, chunks = client.images.build(
            path=str(context),
            dockerfile=dockerfile.name,
            tag=tag,
            rm=True,
            forcerm=True,
            pull=False,
            container_limits={"memory": BUILD_MEMORY_BYTES, "memswap": BUILD_MEMORY_BYTES},
            labels={"patchground": "1"},
        )
        log = _log_text(chunks)
    except docker.errors.BuildError as exc:
        log = _log_text(exc.build_log)
        raise BuildFailed(log or str(exc.msg)) from exc
    except docker.errors.APIError as exc:
        raise BuildFailed(str(exc)) from exc
    except (docker.errors.DockerException, requests.exceptions.RequestException) as exc:
        raise SandboxError(f"image build did not complete: {exc}") from exc
    finally:
        client.close()
    if image.id is None:
        raise SandboxError("engine returned an image without an id")
    return BuildResult(image_id=image.id, tag=tag, log=log)
