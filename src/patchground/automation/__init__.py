"""Committed-input validation automation; never executes checkout code on the host."""

from patchground.automation.workflow import AutomationResult, validate_changes

__all__ = ["AutomationResult", "validate_changes"]
