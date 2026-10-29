"""patchground.sandbox — see SPEC.md in this folder.

The only module that talks to the container engine. Its API takes plain values (paths, strings,
limits) and returns plain results; it knows nothing about sessions, packs or reports.
"""

from patchground.sandbox.build import BuildResult, build_image
from patchground.sandbox.errors import BuildFailed, EngineUnavailable, JUnitError, SandboxError
from patchground.sandbox.junit import TestResult, TestStatus, parse_junit
from patchground.sandbox.run import Limits, RunOutcome, RunResult, run_check

__all__ = [
    "BuildFailed",
    "BuildResult",
    "EngineUnavailable",
    "JUnitError",
    "Limits",
    "RunOutcome",
    "RunResult",
    "SandboxError",
    "TestResult",
    "TestStatus",
    "build_image",
    "parse_junit",
    "run_check",
]
