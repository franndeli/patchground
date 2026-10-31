"""Run the supported ``patchground-contract-verification`` gates for a challenge folder.

Steps run in order and stop at the first failure; later steps are reported as ``not_run``.
Anti-gaming reports ``not_run`` for unsupported runners or editable-test layouts. Problems with the
host (engine unreachable, git missing, engine failures) are not verdicts on the challenge and
raise :class:`VerifyEnvironmentError` instead of failing a step.

The challenge folder is only read, except for ``verification.json``, written on success. The
reference solution is applied to a copy in the system temp directory.
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from ruamel.yaml import YAML

from patchground import sandbox
from patchground.sandbox import (
    BuildFailed,
    BuildResult,
    EngineUnavailable,
    Limits,
    RunOutcome,
    RunResult,
    SandboxError,
    TestStatus,
)
from patchground.spec import Challenge, ManifestError, ManifestIssue, load_challenge
from patchground.verify.errors import VerifyEnvironmentError
from patchground.verify.record import (
    VERIFICATION_FILE,
    remove_verification,
    verification_document,
    write_verification,
)
from patchground.verify.reference import PatchError, apply_patch, copy_workspace, snapshot
from patchground.verify.result import (
    RunSummary,
    StepName,
    StepResult,
    StepStatus,
    ValidationReport,
    format_ids,
    run_label,
    utc_now,
)
from patchground.verify.tampering import (
    Mutation,
    UnsupportedTampering,
    mutate,
    supports_pytest,
    test_modules,
)

DEFAULT_LIMITS = Limits()
BUILD_LOG_TAIL_LINES = 30
INCONCLUSIVE = frozenset({RunOutcome.MISSING_RESULTS, RunOutcome.LIMIT_EXCEEDED})
SERVICES_UNSUPPORTED = (
    "environment.services is not supported yet (deferred beyond the local prototype)"
)

Progress = Callable[[str], None]


class Sandbox(Protocol):
    """The two sandbox operations validation needs (injectable for tests)."""

    def build_image(self, dockerfile: Path, *, name: str) -> BuildResult: ...

    def run_check(
        self, image_id: str, layers: Sequence[Path], command: str, *, limits: Limits
    ) -> RunResult: ...


class DockerSandbox:
    """The real sandbox: :mod:`patchground.sandbox`."""

    def build_image(self, dockerfile: Path, *, name: str) -> BuildResult:
        return sandbox.build_image(dockerfile, name=name)

    def run_check(
        self, image_id: str, layers: Sequence[Path], command: str, *, limits: Limits
    ) -> RunResult:
        return sandbox.run_check(image_id, layers, command, limits=limits)


class _StepFailed(Exception):
    def __init__(self, result: StepResult) -> None:
        super().__init__(result.detail)
        self.result = result


@dataclass(frozen=True)
class _Layer:
    label: str
    path: Path


# --------------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------------


def validate_challenge(
    folder: Path | str,
    *,
    limits: Limits = DEFAULT_LIMITS,
    write: bool = True,
    sandbox: Sandbox | None = None,
    progress: Progress | None = None,
    yes: bool = False,
    expected_identity: str | None = None,
    pack_root: Path | None = None,
) -> ValidationReport:
    """Authorize installed inputs; validate their captured copy without altering the cache."""
    from patchground.packs.models import ConsentRequired, PackError
    from patchground.packs.registry import prepare_execution

    try:
        with prepare_execution(
            folder, yes=yes, expected_identity=expected_identity, root=pack_root
        ) as prepared:
            report = _validate_challenge(
                prepared.path,
                limits=limits,
                write=write and prepared.pack is None,
                sandbox=sandbox,
                progress=progress,
                input_roots=prepared.input_roots,
            )
            if prepared.pack is not None:
                challenge = (
                    replace(
                        report.challenge,
                        root=prepared.source_path,
                        manifest_path=prepared.source_path / "challenge.yaml",
                    )
                    if report.challenge is not None
                    else None
                )
                report = replace(report, folder=prepared.source_path, challenge=challenge)
            return report
    except ConsentRequired:
        raise
    except PackError as exc:
        raise VerifyEnvironmentError(str(exc)) from exc


def _validate_challenge(
    folder: Path,
    *,
    limits: Limits = DEFAULT_LIMITS,
    write: bool = True,
    sandbox: Sandbox | None = None,
    progress: Progress | None = None,
    input_roots: tuple[Path, ...] = (),
) -> ValidationReport:
    """Validate the challenge in ``folder`` and return the per-step report.

    On success (every executed step passed) and with ``write``, ``verification.json`` is written
    atomically into the challenge root and its path recorded in the report. On failure with
    ``write``, an existing ``verification.json`` is deleted so no stale record claims validity.
    ``progress`` receives short status messages while long steps run.

    Raises :class:`VerifyEnvironmentError` when the host cannot run validation.
    """
    folder = Path(folder)
    box: Sandbox = sandbox if sandbox is not None else DockerSandbox()
    notify: Progress = progress if progress is not None else _ignore
    run = _Validation(folder, box, limits, notify, input_roots=input_roots)
    steps = run.execute()
    report = ValidationReport(
        folder=folder,
        steps=tuple(steps),
        validated_at=utc_now(),
        challenge=run.challenge,
        image_id=run.image_id,
    )
    if report.valid and write and run.challenge is not None:
        try:
            path = write_verification(run.challenge.root, verification_document(report))
        except OSError as exc:
            raise VerifyEnvironmentError(
                f"the challenge is valid but {VERIFICATION_FILE} could not be written: {exc}"
            ) from exc
        report = replace(report, verification_file=path)
    elif not report.valid and write:
        try:
            removed = remove_verification(folder)
        except OSError as exc:
            raise VerifyEnvironmentError(
                f"validation failed at step {_failed_name(report)} and the stale "
                f"{VERIFICATION_FILE} could not be removed: {exc}"
            ) from exc
        report = replace(report, removed_verification_file=removed)
    return report


def _failed_name(report: ValidationReport) -> str:
    failed = report.failed_step
    return failed.value if failed is not None else "unknown"


def _ignore(_message: str) -> None:
    return None


class _Validation:
    """State shared between the steps of one validation."""

    def __init__(
        self,
        folder: Path,
        box: Sandbox,
        limits: Limits,
        progress: Progress,
        *,
        input_roots: tuple[Path, ...] = (),
    ) -> None:
        self.folder = folder
        self.input_roots = input_roots
        self.box = box
        self.limits = limits
        self.progress = progress
        self.challenge: Challenge | None = None
        self.image_id: str | None = None
        self.hidden_ids: list[str] = []
        self.starting_ids: list[str] = []
        self.baselines: list[RunSummary] = []

    def execute(self) -> list[StepResult]:
        ordered: list[tuple[StepName, Callable[[str], StepResult]]] = [
            (StepName.MANIFEST, self._manifest),
            (StepName.BUILD, self._build),
            (StepName.BROKEN_FAILS, self._broken_fails),
            (StepName.REFERENCE_PASSES, self._reference_passes),
            (StepName.DETERMINISM, self._determinism),
            (StepName.ANTI_GAMING, self._anti_gaming),
        ]
        results: list[StepResult] = []
        failed: StepName | None = None
        for name, step in ordered:
            if failed is not None:
                detail = f"not run: step {failed.value} failed"
                results.append(StepResult(name, StepStatus.NOT_RUN, detail))
                continue
            started = utc_now()
            try:
                result = step(started)
            except _StepFailed as exc:
                result = exc.result
            results.append(result)
            if name in (StepName.BROKEN_FAILS, StepName.REFERENCE_PASSES):
                self.baselines.extend(result.runs)
            if result.status is StepStatus.FAILED:
                failed = name
        return results

    # ---------------------------------------------------------------------------------- helpers

    def _loaded(self) -> Challenge:
        if self.challenge is None:  # pragma: no cover - guarded by fail-fast ordering
            raise RuntimeError("challenge not loaded")
        return self.challenge

    def _check_layers(self) -> list[_Layer]:
        challenge = self._loaded()
        checks = challenge.manifest.checks
        layers: list[_Layer] = []
        if checks.visible is not None:
            layers.append(_Layer("checks.visible", challenge.root / checks.visible))
        layers.append(_Layer("checks.hidden", challenge.root / checks.hidden))
        return layers

    def _run(
        self,
        step: StepName,
        started: str,
        label: str,
        layers: Sequence[_Layer],
        runs: Sequence[RunSummary],
    ) -> tuple[RunResult, RunSummary]:
        problem = _layer_problem(layers)
        if problem is not None:
            raise _StepFailed(_failed(step, started, problem, runs))
        if self.image_id is None:  # pragma: no cover - guarded by fail-fast ordering
            raise RuntimeError("image not built")
        command = self._loaded().manifest.environment.test_command
        try:
            result = self.box.run_check(
                self.image_id, [layer.path for layer in layers], command, limits=self.limits
            )
        except EngineUnavailable as exc:
            raise VerifyEnvironmentError(str(exc)) from exc
        except SandboxError as exc:
            raise VerifyEnvironmentError(f"sandbox error during run {label!r}: {exc}") from exc
        summary = RunSummary.from_result(label, result)
        if result.outcome in INCONCLUSIVE:
            detail = f"inconclusive: run {label} {_inconclusive_reason(result)}"
            raise _StepFailed(_failed(step, started, detail, [*runs, summary]))
        return result, summary

    # ------------------------------------------------------------------------------------ steps

    def _manifest(self, started: str) -> StepResult:
        self.progress("loading challenge.yaml")
        try:
            challenge = load_challenge(self.folder)
        except ManifestError as exc:
            count = len(exc.issues)
            detail = f"{count} problem{'s' if count != 1 else ''} in the challenge manifest"
            return _manifest_failure(started, detail, exc.issues)
        services = challenge.manifest.environment.services
        if services:
            manifest_file = self.folder / challenge.manifest_path.name
            issue = ManifestIssue(
                manifest_file,
                _services_line(challenge.manifest_path),
                "environment.services",
                "not supported yet (deferred beyond the local prototype); use [] until then",
            )
            return _manifest_failure(started, SERVICES_UNSUPPORTED, [issue])
        self.challenge = challenge
        manifest = challenge.manifest
        detail = f"challenge.yaml is valid ({manifest.id} {manifest.version})"
        return StepResult(StepName.MANIFEST, StepStatus.PASSED, detail, started, utc_now())

    def _build(self, started: str) -> StepResult:
        challenge = self._loaded()
        dockerfile = challenge.root / challenge.manifest.environment.dockerfile
        self.progress("building image (the first build may take a while)")
        try:
            built = self.box.build_image(dockerfile, name=challenge.manifest.id)
        except BuildFailed as exc:
            tail = "\n".join(exc.log.rstrip("\n").splitlines()[-BUILD_LOG_TAIL_LINES:])
            return StepResult(
                StepName.BUILD,
                StepStatus.FAILED,
                "image build failed",
                started,
                utc_now(),
                log_tail=tail,
            )
        except EngineUnavailable as exc:
            raise VerifyEnvironmentError(str(exc)) from exc
        except SandboxError as exc:
            raise VerifyEnvironmentError(str(exc)) from exc
        self.image_id = built.image_id
        return StepResult(
            StepName.BUILD, StepStatus.PASSED, f"built {built.tag}", started, utc_now()
        )

    def _broken_fails(self, started: str) -> StepResult:
        step = StepName.BROKEN_FAILS
        workspace = _Layer("workspace", self._loaded().root / "workspace")
        checks = self._check_layers()
        visible = [layer for layer in checks if layer.label == "checks.visible"]
        labels = ["workspace"] + (["visible"] if visible else [])

        self.progress("running checks on the starting workspace")
        first, first_summary = self._run(
            step, started, run_label(*labels), [workspace, *visible], []
        )
        _, all_summary = self._run(
            step, started, run_label(*labels, "hidden"), [workspace, *checks], [first_summary]
        )
        runs = (first_summary, all_summary)

        before = {t.id for t in first.tests}
        after = {t.id for t in all_summary.tests}
        vanished = list(dict.fromkeys(t.id for t in first.tests if t.id not in after))
        if vanished:
            detail = (
                "inconclusive: hidden checks changed or deselected visible tests: "
                f"{format_ids(vanished)}"
            )
            return _failed(step, started, detail, runs)
        hidden = [t for t in all_summary.tests if t.id not in before]
        if not hidden:
            detail = "no hidden tests detected: hidden checks must add tests"
            return _failed(step, started, detail, runs)
        failing = [t for t in hidden if t.status in (TestStatus.FAILED, TestStatus.ERRORED)]
        if not failing:
            detail = (
                f"the starting workspace passes every hidden check ({len(hidden)} hidden "
                "tests, none failed or errored)"
            )
            return _failed(step, started, detail, runs)
        self.hidden_ids = [t.id for t in hidden]
        self.starting_ids = list(dict.fromkeys(t.id for t in first.tests))
        detail = (
            f"{len(failing)} of {len(hidden)} hidden tests fail on the starting workspace; "
            f"run {first_summary.label}: {_counts_text(first_summary)}"
        )
        return StepResult(step, StepStatus.PASSED, detail, started, utc_now(), runs=runs)

    @contextmanager
    def _reference_workspace(
        self, step: StepName, started: str, runs: Sequence[RunSummary]
    ) -> Iterator[Path]:
        challenge = self._loaded()
        patch = challenge.root / challenge.manifest.solution
        try:
            temp_root = Path(tempfile.mkdtemp(prefix="patchground-reference-")).resolve()
        except OSError as exc:
            raise VerifyEnvironmentError(f"could not create a temporary folder: {exc}") from exc
        try:
            copy = temp_root / "workspace"
            copy_workspace(challenge.root / "workspace", copy)
            before = snapshot(copy)
            self.progress("applying reference.patch")
            try:
                apply_patch(patch, copy, temp_root, inputs=(challenge.root, *self.input_roots))
            except PatchError as exc:
                detail = f"reference.patch does not apply with git apply -p1: {exc.stderr}"
                raise _StepFailed(_failed(step, started, detail, runs)) from exc
            if snapshot(copy) == before:
                raise _StepFailed(
                    _failed(step, started, "reference.patch applied but changed no files", runs)
                )
            yield copy
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def _reference_passes(self, started: str) -> StepResult:
        step = StepName.REFERENCE_PASSES
        with self._reference_workspace(step, started, []) as copy:
            self.progress("running checks with reference.patch applied")
            checks = self._check_layers()
            has_visible = any(layer.label == "checks.visible" for layer in checks)
            label = run_label("reference", *(["visible"] if has_visible else []), "hidden")
            layers = [_Layer("the patched workspace (reference.patch)", copy), *checks]
            result, summary = self._run(step, started, label, layers, [])

        runs = (summary,)
        if not result.tests:
            return _failed(step, started, "the reference run reported no tests", runs)
        present = {t.id for t in result.tests}
        missing_hidden = [test_id for test_id in self.hidden_ids if test_id not in present]
        if missing_hidden:
            detail = f"hidden tests missing from the reference run: {format_ids(missing_hidden)}"
            return _failed(step, started, detail, runs)
        missing = [test_id for test_id in self.starting_ids if test_id not in present]
        if missing:
            detail = (
                "tests of the starting-state run missing from the reference run: "
                f"{format_ids(missing)}"
            )
            return _failed(step, started, detail, runs)
        not_passing = [
            f"{t.id} ({t.status.value})" for t in summary.tests if t.status is not TestStatus.PASSED
        ]
        if not_passing:
            detail = (
                f"{len(not_passing)} of {len(summary.tests)} tests do not pass with "
                f"reference.patch applied: {format_ids(not_passing)}"
            )
            return _failed(step, started, detail, runs)
        detail = (
            f"all {len(summary.tests)} tests pass with reference.patch applied "
            f"({len(self.hidden_ids)} hidden)"
        )
        return StepResult(step, StepStatus.PASSED, detail, started, utc_now(), runs=runs)

    def _determinism(self, started: str) -> StepResult:
        step = StepName.DETERMINISM
        runs = [replace(run, label=f"round-1:{run.label}") for run in self.baselines]
        workspace = _Layer("workspace", self._loaded().root / "workspace")
        checks = self._check_layers()
        visible = [layer for layer in checks if layer.label == "checks.visible"]

        def repeat(round_number: int, baseline: RunSummary, layers: Sequence[_Layer]) -> None:
            label = f"round-{round_number}:{baseline.label}"
            self.progress(f"checking determinism: {label}")
            _, summary = self._run(step, started, label, layers, runs)
            runs.append(summary)
            expected = sorted((test.id, test.status.value) for test in baseline.tests)
            actual = sorted((test.id, test.status.value) for test in summary.tests)
            if summary.outcome != baseline.outcome or actual != expected:
                raise _StepFailed(_failed(step, started, f"run {label} differs from round 1", runs))

        for round_number in (2, 3):
            repeat(round_number, self.baselines[0], [workspace, *visible])
            repeat(round_number, self.baselines[1], [workspace, *checks])
            with self._reference_workspace(step, started, runs) as copy:
                repeat(
                    round_number,
                    self.baselines[2],
                    [_Layer("the patched workspace (reference.patch)", copy), *checks],
                )
        return StepResult(
            step,
            StepStatus.PASSED,
            "identical per-test results across 3 runs of each workspace variant",
            started,
            utc_now(),
            runs=tuple(runs),
        )

    def _anti_gaming(self, started: str) -> StepResult:
        step = StepName.ANTI_GAMING
        challenge = self._loaded()
        runs: list[RunSummary] = []
        visible_ids = set(self.baselines[0].ids())
        expected = Counter(
            (test.id, test.status) for test in self.baselines[1].tests if test.id not in visible_ids
        )
        try:
            if not supports_pytest(challenge.manifest.environment.test_command):
                raise UnsupportedTampering("runner is not a supported direct pytest invocation")
            if not visible_ids:
                raise UnsupportedTampering("no editable baseline tests were observed")
            with tempfile.TemporaryDirectory(prefix="patchground-anti-gaming-") as temporary:
                root = Path(temporary).resolve()
                checks = self._check_layers()
                editable = [_Layer("workspace", challenge.root / "workspace")]
                editable.extend(layer for layer in checks if layer.label == "checks.visible")
                hidden = [layer for layer in checks if layer.label == "checks.hidden"]
                mutations: tuple[Mutation, ...] = ("empty", "deleted", "skipped")
                for mutation in mutations:
                    label = f"anti-{mutation}"
                    parent = root / label
                    parent.mkdir()
                    copies: list[_Layer] = []
                    for index, layer in enumerate(editable):
                        copy = parent / f"layer-{index}"
                        copy_workspace(layer.path, copy)
                        copies.append(_Layer(layer.label, copy))
                    problem = _layer_problem([*copies, *hidden])
                    if problem is not None:
                        return _failed(step, started, problem, runs)
                    modules = test_modules([layer.path for layer in copies])
                    if not modules:
                        raise UnsupportedTampering("no conventional editable pytest modules found")
                    mutate(modules, mutation)
                    self.progress(f"checking editable-test tampering: {label}")
                    _, summary = self._run(step, started, label, [*copies, *hidden], runs)
                    runs.append(summary)
                    actual = Counter(
                        (test.id, test.status)
                        for test in summary.tests
                        if test.id not in visible_ids
                    )
                    if actual != expected:
                        return _failed(
                            step,
                            started,
                            f"run {label} changed hidden test identities, counts or statuses",
                            runs,
                        )
                    if mutation == "deleted" and visible_ids <= set(summary.ids()):
                        raise UnsupportedTampering("deleted modules did not remove editable tests")
                    if mutation == "skipped":
                        previously_active = {
                            test.id
                            for test in self.baselines[0].tests
                            if test.status is not TestStatus.SKIPPED
                        }
                        if not any(
                            test.id in previously_active and test.status is TestStatus.SKIPPED
                            for test in summary.tests
                        ):
                            raise UnsupportedTampering("skip mutation did not skip editable tests")
        except UnsupportedTampering as exc:
            return StepResult(
                step,
                StepStatus.NOT_RUN,
                f"not verified: {exc}",
                started,
                utc_now(),
                runs=tuple(runs),
            )
        except OSError as exc:
            raise VerifyEnvironmentError("anti-gaming temporary files are unavailable") from exc
        return StepResult(
            step,
            StepStatus.PASSED,
            "hidden outcomes unchanged under empty diff and "
            "editable pytest module deletion/skipping",
            started,
            utc_now(),
            runs=tuple(runs),
        )


# --------------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------------


def _failed(
    step: StepName,
    started: str,
    detail: str,
    runs: Sequence[RunSummary],
    *,
    notes: Sequence[str] = (),
) -> StepResult:
    return StepResult(
        step, StepStatus.FAILED, detail, started, utc_now(), runs=tuple(runs), notes=tuple(notes)
    )


def _manifest_failure(started: str, detail: str, issues: Sequence[ManifestIssue]) -> StepResult:
    cwd = Path.cwd()
    return StepResult(
        StepName.MANIFEST,
        StepStatus.FAILED,
        detail,
        started,
        utc_now(),
        issues=tuple(issues),
        issue_lines=tuple(issue.format(relative_to=cwd) for issue in issues),
    )


def _services_line(manifest_path: Path) -> int | None:
    """1-based line of the ``services`` key under ``environment``, if it can be found."""
    try:
        data: Any = YAML(typ="rt", pure=True).load(manifest_path.read_text(encoding="utf-8"))
        line = data["environment"].lc.key("services")[0]
    except Exception:  # best effort: the manifest already validated; fall back to no line
        return None
    return line + 1 if isinstance(line, int) else None


def _inconclusive_reason(result: RunResult) -> str:
    if result.outcome is RunOutcome.LIMIT_EXCEEDED:
        return f"exceeded the {result.limit or 'resource'} limit"
    return "produced no usable junit.xml (missing results)"


def _counts_text(summary: RunSummary) -> str:
    return ", ".join(
        f"{summary.count(status)} {status.value}"
        for status in TestStatus
        if summary.count(status) or status is TestStatus.PASSED
    )


def _layer_problem(layers: Sequence[_Layer]) -> str | None:
    """Mirror the sandbox's layer rules so challenge problems fail a step, not the engine.

    Rejects symlinks and special files, and any non-directory path provided by two layers.
    """
    seen: dict[str, tuple[str, bool]] = {}
    for layer in layers:
        for current, dirnames, filenames in os.walk(layer.path):
            base = Path(current)
            for name in [*dirnames, *filenames]:
                path = base / name
                rel = path.relative_to(layer.path).as_posix()
                mode = path.lstat().st_mode
                if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                    kind = "a symlink" if stat.S_ISLNK(mode) else "a special file"
                    return f"'{rel}' in {layer.label} is {kind}; only regular files are allowed"
                is_dir = stat.S_ISDIR(mode)
                previous = seen.get(rel)
                if previous is not None and not (previous[1] and is_dir):
                    return (
                        f"'{rel}' is provided by both {previous[0]} and {layer.label}; check "
                        "files are merged into the workspace root and must not collide"
                    )
                seen.setdefault(rel, (layer.label, is_dir))
    return None
