"""Versioned storage and public, log-free session results."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field, model_validator

from patchground.packs.models import PackIdentity
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
    trust: Literal["local-authored", "unofficial"] = "local-authored"
    pack: PackIdentity | None = None
    image_id: str = Field(min_length=1)
    started_at: AwareDatetime
    timer: bool
    history_enabled: bool = False

    @model_validator(mode="after")
    def consistent_pack(self) -> SessionRecord:
        if (self.pack is None) != (self.trust == "local-authored"):
            raise ValueError("inconsistent pack provenance")
        return self


class CheckTest(Model):
    id: str
    status: TestStatus


class SnapshotStatus(Model):
    state: Literal["recorded", "unavailable", "disabled"]
    ref: str | None = None
    detail: Literal["Checkpoint capture unavailable"] | None = None


class HistoryEntry(Model):
    ref: str
    commit: str
    kind: Literal["initial", "check"]
    ts: AwareDatetime
    check_outcome: str | None = None


class HistoryResult(Model):
    session: Path
    enabled: bool
    availability: Literal["available", "disabled", "unavailable"]
    snapshots: tuple[HistoryEntry, ...]


class CheckResult(Model):
    outcome: RunOutcome
    tests: tuple[CheckTest, ...]
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    limit: Literal["timeout", "memory"] | None = None
    history: SnapshotStatus | None = None

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
    pack: PackIdentity | None = None
    history: SnapshotStatus | None = None


class ResetResult(Model):
    session: Path
    workspace: Path
    challenge_id: str


class SessionStatus(Model):
    session: Path
    workspace: Path
    challenge_id: str
    timer: bool
    state: Literal["active", "submitted"] = "active"
    submitted_at: AwareDatetime | None = None
    elapsed_seconds: float
    timebox_minutes: int
    last_check: CheckResult | None
    last_outcome: str | None


def now() -> datetime:
    return datetime.now(UTC)
