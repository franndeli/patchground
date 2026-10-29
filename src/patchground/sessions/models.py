"""Versioned storage and public, log-free session results."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field

from patchground.sandbox import RunOutcome, TestStatus


class SessionError(Exception):
    """Invalid input, unsafe session storage, or unavailable infrastructure."""


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionRecord(Model):
    schema_version: Literal[1] = 1
    challenge_id: str
    challenge_version: str
    source: str
    trust: Literal["local-authored"] = "local-authored"
    image_id: str = Field(min_length=1)
    started_at: AwareDatetime
    timer: bool


class CheckTest(Model):
    id: str
    status: TestStatus


class CheckResult(Model):
    outcome: RunOutcome
    tests: tuple[CheckTest, ...]
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    limit: Literal["timeout", "memory"] | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        return (
            self.outcome == RunOutcome.PASSED
            and bool(self.tests)
            and all(test.status == TestStatus.PASSED for test in self.tests)
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def counts(self) -> dict[str, int]:
        return {status.value: sum(t.status == status for t in self.tests) for status in TestStatus}


class Event(Model):
    ts: AwareDatetime
    type: str
    data: dict[str, object]


class StartedSession(Model):
    session: Path
    workspace: Path
    challenge_id: str
    timer: bool
    ticket: str


class SessionStatus(Model):
    session: Path
    workspace: Path
    challenge_id: str
    timer: bool
    elapsed_seconds: float
    timebox_minutes: int
    last_check: CheckResult | None
    last_outcome: str | None


def now() -> datetime:
    return datetime.now(UTC)
