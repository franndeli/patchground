"""Versioned, round-trippable verified-outcome records; no overall score."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from patchground.report.analysis import DiffEvidence, Fact, StructureEvidence
from patchground.report.regression import RegressionEvidence
from patchground.sandbox import RunOutcome
from patchground.sessions import CheckResult
from patchground.sessions.models import CheckTest


class CheckEvidence(Fact):
    outcome: RunOutcome
    tests: tuple[CheckTest, ...]
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    limit: Literal["timeout", "memory"] | None
    passed: bool
    counts: dict[str, int]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        canonical = CheckResult(
            outcome=self.outcome,
            tests=self.tests,
            duration_seconds=self.duration_seconds,
            limit=self.limit,
        )
        if self.passed != canonical.passed or self.counts != canonical.counts:
            raise ValueError("inconsistent check evidence")
        return self

    @classmethod
    def from_result(cls, result: CheckResult) -> Self:
        return cls.model_validate(result.model_dump(mode="json"))


class EffortEvidence(Fact):
    timer_enabled: bool
    elapsed_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    timebox_minutes: int = Field(gt=0)
    practice_checks: int = Field(ge=0)
    hints_revealed: int = Field(ge=0)


class VerifiedReport(Fact):
    schema_version: Literal[1] = 1
    challenge_id: str
    challenge_version: str
    image_id: str
    submitted_at: AwareDatetime
    checks: CheckEvidence
    regression: RegressionEvidence
    diff: DiffEvidence
    test_structure: StructureEvidence
    effort: EffortEvidence
