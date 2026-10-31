"""Apply ``reference.patch`` to a temporary copy of the starting workspace with host git.

``git apply`` here is not a challenge command: it only edits files in a copy that lives in the
system temp directory, outside any repository. Git must never read configuration the challenge
controls: a ``.git`` inside the workspace could define ``filter.*.clean``/``smudge`` commands that
``.gitattributes`` would make git run on the host. So the copy never contains ``.git`` entries
(:func:`copy_workspace`), and git runs with ``GIT_DIR`` pointing at a fresh, empty bare repository
created next to the copy (no discovery at all), with ``GIT_CEILING_DIRECTORIES`` as a second fence,
system and global config and system attributes ignored, and hooks, fsmonitor and the attributes
file disabled. ``--unsafe-paths`` is never passed, so the patch cannot touch anything outside the
copy.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from patchground import safeio
from patchground.verify.errors import VerifyEnvironmentError

GIT_TIMEOUT_SECONDS = 60.0


class PatchError(Exception):
    """``git apply`` rejected the patch; ``stderr`` is git's explanation."""

    def __init__(self, stderr: str) -> None:
        super().__init__(stderr)
        self.stderr = stderr


def snapshot(directory: Path) -> dict[str, str]:
    """Map relative POSIX path -> sha256 of the content for every non-directory entry.

    Symlinks are recorded by their target text and never followed.
    """
    entries: dict[str, str] = {}
    for current, dirnames, filenames in directory.walk(follow_symlinks=False):
        names = filenames + [d for d in dirnames if (current / d).is_symlink()]
        for name in names:
            path = current / name
            rel = path.relative_to(directory).as_posix()
            if path.is_symlink():
                entries[rel] = "L" + hashlib.sha256(os.fsencode(path.readlink())).hexdigest()
            elif stat.S_ISREG(path.lstat().st_mode):
                entries[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                entries[rel] = "special"
    return entries


def _is_git_entry(name: str) -> bool:
    return name.casefold() == ".git"


def _ignore_git(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if _is_git_entry(name)}


def copy_workspace(source: Path, target: Path) -> None:
    """Copy ``source`` to the new directory ``target`` without any ``.git`` entry (any case/depth).

    Symlinks are copied as symlinks. Raises :class:`VerifyEnvironmentError` if the copy fails.
    """
    try:
        shutil.copytree(source, target, symlinks=True, ignore=_ignore_git)
    except (OSError, shutil.Error) as exc:
        raise VerifyEnvironmentError(
            f"could not copy the workspace to a temporary folder: {exc}"
        ) from exc


_GIT_HARDENING = (
    "-c",
    f"core.hooksPath={os.devnull}",
    "-c",
    "core.fsmonitor=false",
    "-c",
    f"core.attributesFile={os.devnull}",
)


def _git_env(temp_root: Path) -> dict[str, str]:
    return {
        "PATH": os.defpath,
        "HOME": str(temp_root),
        "LC_ALL": "C",
        "GIT_CEILING_DIRECTORIES": str(temp_root.parent),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(*inputs: Path) -> str:
    return safeio.resolve_git(*inputs, error=VerifyEnvironmentError)


def apply_patch(
    patch: Path, target: Path, temp_root: Path, *, inputs: tuple[Path, ...] = ()
) -> None:
    """Apply ``patch`` (paths relative to ``target``, ``-p1``) inside ``target``.

    ``temp_root`` is the temporary directory that contains ``target``; an empty bare repository
    is created there (outside ``target``) and used as ``GIT_DIR``, so git never discovers or
    reads any other repository, including a ``.git`` inside ``target``. Raises
    :class:`PatchError` if git rejects the patch and :class:`VerifyEnvironmentError` if git is
    missing or cannot run.
    """
    git = _git(patch.parent, target, temp_root, *inputs)
    target = target.resolve()
    env = _git_env(temp_root)
    try:
        git_dir = Path(tempfile.mkdtemp(prefix="gitdir-", dir=temp_root)).resolve()
    except OSError as exc:
        raise VerifyEnvironmentError(f"could not create a temporary git directory: {exc}") from exc
    if git_dir.is_relative_to(target):
        raise ValueError("temp_root must not lie inside the target")
    init = _run_git(
        [git, *_GIT_HARDENING, "init", "--bare", "-q", "--template=", str(git_dir)], temp_root, env
    )
    if init.returncode != 0:
        raise VerifyEnvironmentError("could not initialize the isolated reference repository")
    env = {**env, "GIT_DIR": str(git_dir), "GIT_WORK_TREE": str(target)}
    patch_arg = str(patch.resolve())
    for argv in (
        [git, *_GIT_HARDENING, "apply", "--check", "-p1", patch_arg],
        [git, *_GIT_HARDENING, "apply", "-p1", "--whitespace=nowarn", patch_arg],
    ):
        completed = _run_git(argv, target, env)
        if completed.returncode != 0:
            raise PatchError(f"git apply exited {completed.returncode}")


def _run_git(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError as exc:
        raise VerifyEnvironmentError(f"could not run git: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise VerifyEnvironmentError(f"git did not finish within {GIT_TIMEOUT_SECONDS:g}s") from exc
