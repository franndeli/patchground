"""Compose frozen submission evidence without changing the user's workspace or Git."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from patchground import sandbox as engine
from patchground.report.analysis import diff_evidence, structural_evidence
from patchground.report.models import CheckEvidence, EffortEvidence, VerifiedReport
from patchground.report.regression import evaluate_regression
from patchground.report.render import render_markdown
from patchground.sandbox import SandboxError
from patchground.sessions import (
    SessionError,
    check_submission,
    commit_submission,
    prepare_submission,
    read_submission,
)
from patchground.sessions.workflow import Sandbox


def _saved(value: dict[str, object]) -> VerifiedReport:
    try:
        return VerifiedReport.model_validate(value)
    except ValidationError as exc:
        raise SessionError("saved report is corrupt or uses an unsupported format") from exc


def submit_session(
    session: Path | None = None, *, root: Path | None = None, sandbox: Sandbox = engine
) -> VerifiedReport:
    try:
        with prepare_submission(session, root=root) as snapshot:
            if snapshot.saved_report is not None:
                return _saved(snapshot.saved_report)
            checked = check_submission(snapshot, sandbox=sandbox)
            regression = evaluate_regression(
                snapshot.original,
                snapshot.final,
                snapshot.record.image_id,
                snapshot.manifest.environment.test_command,
                sandbox=sandbox,
            )
            report = VerifiedReport(
                challenge_id=snapshot.record.challenge_id,
                challenge_version=snapshot.record.challenge_version,
                image_id=snapshot.record.image_id,
                submitted_at=snapshot.requested_at,
                checks=CheckEvidence.from_result(checked),
                regression=regression,
                diff=diff_evidence(
                    snapshot.original, snapshot.final, tuple(snapshot.manifest.expected_paths)
                ),
                test_structure=structural_evidence(
                    snapshot.original, snapshot.final, snapshot.manifest.environment.test_command
                ),
                effort=EffortEvidence(
                    timer_enabled=snapshot.record.timer,
                    elapsed_seconds=max(
                        0.0, (snapshot.requested_at - snapshot.record.started_at).total_seconds()
                    )
                    if snapshot.record.timer
                    else None,
                    timebox_minutes=snapshot.manifest.timebox_minutes,
                    practice_checks=sum(event.type == "check_run" for event in snapshot.events),
                    hints_revealed=sum(event.type == "hint_revealed" for event in snapshot.events),
                ),
            )
            commit_submission(
                snapshot, report.model_dump(mode="json"), render_markdown(report), checked
            )
            return report
    except (OSError, UnicodeError, SandboxError) as exc:
        raise SessionError("submission unavailable: storage or frozen image unavailable") from exc


def saved_report(session: Path | None = None, *, root: Path | None = None) -> VerifiedReport:
    try:
        return _saved(read_submission(session, root=root))
    except (OSError, UnicodeError) as exc:
        raise SessionError("report unavailable: invalid session storage") from exc
