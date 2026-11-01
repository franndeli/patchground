"""Create a runnable challenge from bundled, non-executable template resources."""

from __future__ import annotations

import os
import re
from contextlib import ExitStack, suppress
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict

from patchground import runner_assets
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


_TYPESCRIPT_FILES = (
    "challenge.yaml",
    "TICKET.md",
    "workspace/package.json",
    "workspace/src/starter.ts",
    "checks/visible/tests/starter.test.ts",
    "checks/hidden/tests/starter-hidden.test.ts",
    "solution/reference.patch",
)
# (type, language) -> bundled template folder and its template-backed relative files. TypeScript
# starters additionally receive the canonical runner environment from `runner_assets`.
_STARTERS = {
    ("debug", "python"): ("python-debug", TEMPLATE_FILES),
    ("feature", "python"): ("python-feature", TEMPLATE_FILES),
    ("debug", "typescript"): ("typescript-debug", _TYPESCRIPT_FILES),
    ("feature", "typescript"): ("typescript-feature", _TYPESCRIPT_FILES),
}


class AuthoringError(Exception):
    """Invalid scaffold input, an occupied destination or unavailable local storage."""


class CreatedChallenge(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    path: Path
    type: Literal["debug", "feature"] = "debug"
    language: Literal["python", "typescript"] = "python"
    files: tuple[str, ...] = TEMPLATE_FILES


def _identity(parent: int, name: str) -> tuple[int, int]:
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    return info.st_dev, info.st_ino


def _runner_environment() -> dict[str, bytes]:
    """Canonical TypeScript environment files, verbatim and keyed by path under environment/."""
    try:
        assets = runner_assets.vitest_assets()
    except Exception as exc:
        raise AuthoringError("TypeScript runner assets are unavailable") from exc
    if "Dockerfile" not in assets:
        raise AuthoringError("TypeScript runner assets are incomplete")
    names = set(assets)
    for name, content in assets.items():
        path = PurePosixPath(name)
        if (
            not isinstance(content, bytes)
            or path.is_absolute()
            or str(path) != name
            or ".." in path.parts
            or "\\" in name
            or any(str(parent) in names for parent in path.parents)
        ):
            raise AuthoringError("TypeScript runner assets are invalid")
    return {f"environment/{name}": content for name, content in assets.items()}


def create_challenge(
    challenge_id: str, *, type_: str = "debug", language: str = "python"
) -> CreatedChallenge:
    """Reserve cwd/id exclusively; never overwrite, run a challenge or initialize Git."""
    if re.fullmatch(SLUG_PATTERN, challenge_id) is None:
        raise AuthoringError("id must use lowercase letters, digits and single hyphens")
    if (type_, language) not in _STARTERS:
        raise AuthoringError("supported templates: --type debug|feature --lang python|typescript")
    folder, names = _STARTERS[(type_, language)]
    template = files("patchground.authoring").joinpath("templates", folder)
    contents = {
        name: template.joinpath(name + ".tmpl")
        .read_bytes()
        .replace(b"__CHALLENGE_ID__", challenge_id.encode("ascii"))
        for name in names
    }
    if language == "typescript":
        contents.update(_runner_environment())
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
    return CreatedChallenge.model_validate(
        {
            "id": challenge_id,
            "path": Path(challenge_id),
            "type": type_,
            "language": language,
            "files": tuple(contents),
        }
    )
