"""Create a runnable challenge from bundled, non-executable template resources."""

from __future__ import annotations

import os
import re
from contextlib import ExitStack, suppress
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from patchground.spec import ManifestError, load_challenge
from patchground.spec.models import SLUG_PATTERN

TEMPLATE_FILES = (
    "challenge.yaml",
    "TICKET.md",
    "workspace/pyproject.toml",
    "workspace/src/starter.py",
    "checks/visible/tests/test_starter.py",
    "checks/hidden/tests/test_starter_hidden.py",
    "environment/Dockerfile",
    "solution/reference.patch",
)


class AuthoringError(Exception):
    """Invalid scaffold input, an occupied destination or unavailable local storage."""


class CreatedChallenge(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    path: Path
    type: Literal["debug"] = "debug"
    language: Literal["python"] = "python"
    files: tuple[str, ...] = TEMPLATE_FILES


def _identity(parent: int, name: str) -> tuple[int, int]:
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    return info.st_dev, info.st_ino


def create_challenge(
    challenge_id: str, *, type_: str = "debug", language: str = "python"
) -> CreatedChallenge:
    """Reserve cwd/id exclusively; never overwrite, run a challenge or initialize Git."""
    if re.fullmatch(SLUG_PATTERN, challenge_id) is None:
        raise AuthoringError("id must use lowercase letters, digits and single hyphens")
    if (type_, language) != ("debug", "python"):
        raise AuthoringError("supported template: --type debug --lang python")
    template = files("patchground.authoring").joinpath("templates", "python-debug")
    contents = {
        name: template.joinpath(name + ".tmpl")
        .read_bytes()
        .replace(b"__CHALLENGE_ID__", challenge_id.encode("ascii"))
        for name in TEMPLATE_FILES
    }
    created: list[tuple[int, str, tuple[int, int], bool]] = []
    with ExitStack() as handles:
        try:
            parent = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            handles.callback(os.close, parent)
            try:
                os.mkdir(challenge_id, mode=0o700, dir_fd=parent)
            except FileExistsError as exc:
                raise AuthoringError(
                    "destination already exists; choose a new challenge id"
                ) from exc
            root_identity = _identity(parent, challenge_id)
            created.append((parent, challenge_id, root_identity, True))
            root = os.open(
                challenge_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            handles.callback(os.close, root)
            directories: dict[tuple[str, ...], int] = {(): root}
            for relative, content in contents.items():
                parts = Path(relative).parts
                for length in range(1, len(parts)):
                    key = parts[:length]
                    if key in directories:
                        continue
                    directory = directories[key[:-1]]
                    os.mkdir(key[-1], mode=0o700, dir_fd=directory)
                    created.append((directory, key[-1], _identity(directory, key[-1]), True))
                    descriptor = os.open(
                        key[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                    )
                    handles.callback(os.close, descriptor)
                    directories[key] = descriptor
                directory = directories[parts[:-1]]
                descriptor = os.open(
                    parts[-1],
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory,
                )
                with os.fdopen(descriptor, "wb") as stream:
                    info = os.fstat(stream.fileno())
                    created.append((directory, parts[-1], (info.st_dev, info.st_ino), False))
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            for directory, name, identity, _is_directory in created:
                if _identity(directory, name) != identity:
                    raise AuthoringError("scaffold destination changed during creation")
            load_challenge(Path(challenge_id))
        except BaseException as exc:
            for directory, name, identity, is_directory in reversed(created):
                with suppress(OSError):
                    if _identity(directory, name) == identity:
                        if is_directory:
                            os.rmdir(name, dir_fd=directory)
                        else:
                            os.unlink(name, dir_fd=directory)
            if isinstance(exc, OSError | ManifestError):
                raise AuthoringError(
                    "could not create the scaffold; check disk space and directory access"
                ) from exc
            raise
    return CreatedChallenge(id=challenge_id, path=Path(challenge_id))
