"""Deterministic Markdown rendering of facts, never source code or raw test output."""

from __future__ import annotations

import html

from patchground.report.models import VerifiedReport


def _text(value: str) -> str:
    printable = "".join(char if char.isprintable() else " " for char in value)
    escaped = html.escape(printable, quote=True)
    for char in ("\\", "`", "*", "_", "[", "]", "#", "|", "!"):
        escaped = escaped.replace(char, "\\" + char)
    return escaped


def render_markdown(report: VerifiedReport) -> str:
    checks = report.checks
    lines = [
        f"# Verified outcomes: {_text(report.challenge_id)}",
        "",
        f"Challenge version: {_text(report.challenge_version)}",
        f"Submitted: {report.submitted_at.isoformat()}",
        "",
        "## Checks",
        "",
        f"Outcome: {checks.outcome.value}; passing: {checks.passed}.",
        ", ".join(f"{name}: {count}" for name, count in sorted(checks.counts.items())),
    ]
    if checks.limit:
        lines.append(f"Resource limit: {checks.limit}.")
    lines.extend(f"- {test.status.value}: {_text(test.id)}" for test in checks.tests)
    lines += [
        "",
        "## Regression test",
        "",
        f"{report.regression.status}: {_text(report.regression.reason)}.",
    ]
    lines.extend(f"- Verified: {_text(test)}" for test in report.regression.verified_tests)
    lines += ["", "## Diff scope", ""]
    if not report.diff.expected_paths:
        lines.append("Expected paths were not declared.")
    if not report.diff.files:
        lines.append("No ordinary checked-file changes.")
    for change in report.diff.files:
        counts = (
            f"+{change.added_lines} -{change.removed_lines}"
            if change.added_lines is not None
            else "line counts not established (binary, non-UTF-8 or over 1 MiB)"
        )
        scope = "; outside expected paths" if change.outside_expected else ""
        lines.append(f"- {_text(change.path)}: {change.kind}, {counts}{scope}")
    lines += [
        "",
        "## Test structure",
        "",
        f"{report.test_structure.status}: {_text(report.test_structure.reason)}.",
        "Structural removals are not a judgment of semantic test strength.",
    ]
    lines.extend(f"- Removed file: {_text(path)}" for path in report.test_structure.removed_files)
    lines.extend(f"- Removed test: {_text(test)}" for test in report.test_structure.removed_tests)
    lines.extend(
        f"- Assertion count reduced: {_text(item.test)} ({item.before} → {item.after})"
        for item in report.test_structure.assertion_reductions
    )
    lines.extend(
        f"- Unsupported source: {_text(path)}" for path in report.test_structure.unsupported_files
    )
    effort = report.effort
    lines += ["", "## Time and effort", ""]
    if effort.elapsed_seconds is None:
        lines.append("Timer off; elapsed time not established.")
    else:
        lines.append(
            f"Elapsed at submission request: {int(effort.elapsed_seconds)}s / "
            f"{effort.timebox_minutes} minutes."
        )
    lines += [
        f"Practice checks: {effort.practice_checks}; hints revealed: {effort.hints_revealed}.",
        "Submission and regression verification runs are separate from practice-check counts.",
        "",
        "No overall score. This report is local evidence, not tamper-proof attestation.",
        "",
    ]
    return "\n".join(lines)
