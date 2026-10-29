"""Exceptions raised by the sandbox module."""

from __future__ import annotations


class SandboxError(Exception):
    """Base class for every sandbox failure that is not a test outcome."""


class EngineUnavailable(SandboxError):
    """The container engine cannot be reached (not running, no socket, no permission)."""


class BuildFailed(SandboxError):
    """The image build failed; ``log`` holds the builder output up to the failure."""

    def __init__(self, log: str) -> None:
        super().__init__("image build failed")
        self.log = log


class JUnitError(SandboxError):
    """A JUnit XML document could not be parsed (malformed, unsafe or wrong root)."""
