"""Structured results of a validation: per-step results and the overall report.

Everything here is plain data with a JSON form (``to_dict``). The JSON form never carries file
contents, the reference patch or logs of runs that include hidden checks: only test ids and
statuses, counts, and short human-readable details.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from patchground.sandbox import RunOutcome, RunResult, TestStatus
from patchground.spec import Challenge, ManifestIssue


class StepName(StrEnum):
    """The verification steps of ``patchground-contract-verification``, in order."""

    MANIFEST = "manifest"
    BUILD = "build"
    BROKEN_FAILS = "broken_fails"
    REFERENCE_PASSES = "reference_passes"
    DETERMINISM = "determinism"
    ANTI_GAMING = "anti_gaming"


class StepStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


def utc_now() -> str:
    """Current UTC time as ISO 8601 with millisecond precision and a ``Z`` suffix."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class TestOutcome:
    """One test of a run: its id and status only."""

    __test__ = False  # not a pytest test class

    id: str
    status: TestStatus

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "status": self.status.value}


@dataclass(frozen=True)
class RunSummary:
    """One sandbox run as recorded by validation (no log text)."""

    label: str
    outcome: RunOutcome
    tests: tuple[TestOutcome, ...]

    @classmethod
    def from_result(cls, label: str, result: RunResult) -> RunSummary:
        return cls(label, result.outcome, tuple(TestOutcome(t.id, t.status) for t in result.tests))

    def count(self, status: TestStatus) -> int:
        return sum(1 for t in self.tests if t.status is status)

    def ids(self) -> list[str]:
        return [t.id for t in self.tests]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "outcome": self.outcome.value,
            "counts": {
                "passed": self.count(TestStatus.PASSED),
                "failed": self.count(TestStatus.FAILED),
                "errored": self.count(TestStatus.ERRORED),
                "skipped": self.count(TestStatus.SKIPPED),
            },
            "tests": [t.to_dict() for t in self.tests],
        }


@dataclass(frozen=True)
class StepResult:
    """Result of one step.

    ``issues``/``issue_lines`` are set for a failed ``manifest`` step (``issue_lines`` are the
    ``file:line: field: message`` renderings, relative to the working directory when possible);
    ``log_tail`` holds the end of the build log for a failed ``build`` step. ``notes`` are
    sandbox explanations (``[patchground]`` lines) for inconclusive runs.
    """

    name: StepName
    status: StepStatus
    detail: str
    started_at: str | None = None
    finished_at: str | None = None
    runs: tuple[RunSummary, ...] = ()
    issues: tuple[ManifestIssue, ...] = ()
    issue_lines: tuple[str, ...] = ()
    log_tail: str | None = None
    notes: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        """The shape stored in ``verification.json``."""
        return {
            "name": self.name.value,
            "status": self.status.value,
            "detail": self.detail,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "runs": [run.to_dict() for run in self.runs],
        }

    def to_dict(self) -> dict[str, Any]:
        """The record shape plus the failure diagnostics that are set."""
        data = self.to_record()
        if self.issues:
            data["issues"] = [
                {
                    "file": str(issue.file),
                    "line": issue.line,
                    "field": issue.field,
                    "message": issue.message,
                    "text": text,
                }
                for issue, text in zip(self.issues, self.issue_lines, strict=True)
            ]
        if self.log_tail is not None:
            data["log_tail"] = self.log_tail
        if self.notes:
            data["notes"] = list(self.notes)
        return data


@dataclass(frozen=True)
class ValidationReport:
    """Outcome of :func:`patchground.verify.validate_challenge`."""

    folder: Path
    steps: tuple[StepResult, ...]
    validated_at: str
    challenge: Challenge | None = None
    image_id: str | None = None
    verification_file: Path | None = field(default=None)
    removed_verification_file: Path | None = field(default=None)

    @property
    def valid(self) -> bool:
        """True when no step failed and at least one step ran."""
        return self.failed_step is None and any(
            step.status is StepStatus.PASSED for step in self.steps
        )

    @property
    def failed_step(self) -> StepName | None:
        for step in self.steps:
            if step.status is StepStatus.FAILED:
                return step.name
        return None

    def step(self, name: StepName) -> StepResult:
        for step in self.steps:
            if step.name is name:
                return step
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        failed = self.failed_step
        return {
            "valid": self.valid,
            "failed_step": failed.value if failed is not None else None,
            "steps": [step.to_dict() for step in self.steps],
            "verification_file": (
                str(self.verification_file) if self.verification_file is not None else None
            ),
            "removed_verification_file": (
                str(self.removed_verification_file)
                if self.removed_verification_file is not None
                else None
            ),
        }


def run_label(*parts: str) -> str:
    return "+".join(parts)


def format_ids(ids: Sequence[str], limit: int = 10) -> str:
    """Comma-separated ids, truncated after ``limit`` with a count of the rest."""
    shown = ", ".join(ids[:limit])
    if len(ids) > limit:
        shown += f", … ({len(ids) - limit} more)"
    return shown
