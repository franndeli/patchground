"""Deterministic verified outcomes; optional coaching never overrides these facts."""

from patchground.report.models import VerifiedReport
from patchground.report.workflow import saved_report, submit_session

__all__ = ["VerifiedReport", "saved_report", "submit_session"]
