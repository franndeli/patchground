"""Select committed challenges and aggregate the existing verifier's safe facts."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from patchground import verify
from patchground.packs.discovery import discover_challenges
from patchground.packs.models import PackError, SourceSnapshot
from patchground.packs.source import fetch_pack
from patchground.packs.store import capture_tree
from patchground.spec import ManifestError, load_challenge, load_pack


@dataclass
class AutomationResult:
    """One JSON-safe outcome, containing no verifier diagnostics or scratch paths."""

    exit_code: int = 0
    commit: str | None = None
    base_commit: str | None = None
    selection_mode: str = "all"
    selected: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    validations: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "patchground-automation",
            "format_version": 1,
            "commit": self.commit,
            "base_commit": self.base_commit,
            "selection_mode": self.selection_mode,
            "status": "failed" if self.exit_code else "validated" if self.selected else "skipped",
            "exit_code": self.exit_code,
            "selected": list(self.selected),
            "unchanged": list(self.unchanged),
            "removed": list(self.removed),
            "validations": list(self.validations),
            "errors": list(self.errors),
        }


@contextmanager
def _snapshot(
    source: Path, *, ref: str = "HEAD"
) -> Iterator[tuple[SourceSnapshot, tuple[Path, ...]]]:
    with fetch_pack(source, ref=ref) as snapshot:
        if not (snapshot.path / "challenge.yaml").is_file():
            yield snapshot, (snapshot.path,)
            return
        # The verifier requires the root folder name to match the manifest id. Git transport's
        # scratch name is not the authored checkout name; preserve that identity in our own copy.
        with TemporaryDirectory(prefix="patchground-automation-") as temporary:
            target = Path(temporary).resolve() / Path(snapshot.source).name
            target.mkdir()
            capture_tree(snapshot.path.resolve(), target, seal=False)
            yield snapshot.model_copy(update={"path": target}), (snapshot.path, target)


def _candidates(root: Path, directory: str) -> list[str]:
    folder = root / directory
    if not folder.is_dir():
        raise ValueError("selected directory is unavailable")
    if (folder / "pack.yaml").exists():
        pack = load_pack(folder)
        paths = [folder / name for name in pack.manifest.challenges]
    elif (folder / "challenge.yaml").exists():
        paths = [folder]
    else:
        discovered = discover_challenges(folder)
        paths = [Path(item.path) for item in discovered.challenges]
        paths.extend(Path(item.path) for item in discovered.invalid)
    # Preflight every candidate, including unchanged ones, before any build.
    for path in paths:
        load_challenge(path)
    return sorted(path.relative_to(root).as_posix() for path in paths)


def _pack_metadata(folder: Path) -> bytes | None:
    manifest = folder / "pack.yaml"
    return manifest.read_bytes() if manifest.is_file() else None


def _manifest_errors(exc: ManifestError, root: Path) -> list[str]:
    return [
        f"{issue.file.relative_to(root).as_posix()}:{issue.line or 1}: "
        "invalid manifest or challenge layout"
        for issue in exc.issues
    ]


def validate_changes(
    source: Path,
    *,
    directory: str = ".",
    base: str | None = None,
    consent: bool = False,
    sandbox: verify.Sandbox | None = None,
) -> AutomationResult:
    """Validate selected raw committed inputs with explicit build consent and no writes."""
    result = AutomationResult()
    relative = PurePosixPath(directory)
    if (
        not directory
        or relative.is_absolute()
        or ".." in relative.parts
        or "\\" in directory
        or ":" in directory
        or any(ord(char) < 32 for char in directory)
    ):
        result.exit_code = 2
        result.errors.append("directory must be a relative path within the committed source")
        return result
    try:
        with _snapshot(Path(source)) as (current, captured_roots):
            result.commit = current.commit
            try:
                candidates = _candidates(current.path, directory)
            except ManifestError as exc:
                result.exit_code = 1
                result.errors = _manifest_errors(exc, current.path)
                return result
            except ValueError:
                result.exit_code = 1
                result.errors.append("selected directory has invalid challenge candidates")
                return result
            if not candidates:
                result.exit_code = 1
                result.errors.append("selected directory has no discoverable challenges")
                return result
            result.selected = candidates
            if base is not None:
                result.selection_mode = "fallback_all"
                try:
                    with _snapshot(Path(source), ref=base) as (previous, _):
                        old = _candidates(previous.path, directory)
                        metadata_changed = _pack_metadata(
                            current.path / directory
                        ) != _pack_metadata(previous.path / directory)
                        result.removed = sorted(set(old) - set(candidates))
                        result.unchanged = [
                            name
                            for name in candidates
                            if name in old
                            and not metadata_changed
                            and capture_tree(
                                (current.path / name).resolve(), None, seal=False
                            ).digest
                            == capture_tree(
                                (previous.path / name).resolve(), None, seal=False
                            ).digest
                        ]
                        result.selected = [
                            name for name in candidates if name not in result.unchanged
                        ]
                        result.base_commit = previous.commit
                        result.selection_mode = "changed"
                except (PackError, ManifestError, ValueError, OSError):
                    # An unusable comparison must never turn into a silent skip.
                    result.selected = candidates
                    result.unchanged = []
                    result.removed = []
            if result.selected and not consent:
                result.exit_code = 2
                result.errors.append("explicit execution consent is required before building")
                return result
            for name in result.selected:
                try:
                    report = verify.validate_challenge(
                        current.path / name,
                        write=False,
                        sandbox=sandbox,
                        input_roots=(Path(current.source), *captured_roots),
                    )
                except verify.VerifyEnvironmentError:
                    result.exit_code = 2
                    result.errors.append(f"{name}: validation infrastructure unavailable")
                    continue
                result.validations.append(
                    {
                        "path": name,
                        "valid": report.valid,
                        "failed_step": report.failed_step.value if report.failed_step else None,
                        "steps": [
                            {
                                "name": step.name.value,
                                "status": step.status.value,
                                "runs": [
                                    {
                                        "label": run.label,
                                        "outcome": run.outcome.value,
                                        "counts": run.to_dict()["counts"],
                                    }
                                    for run in step.runs
                                ],
                            }
                            for step in report.steps
                        ],
                    }
                )
                if not report.valid and result.exit_code == 0:
                    result.exit_code = 1
    except (PackError, OSError):
        result.exit_code = 2
        result.errors.append("committed source could not be read safely")
    return result
