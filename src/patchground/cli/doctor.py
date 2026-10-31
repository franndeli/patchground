"""`pgnd doctor`: diagnose engine, Git and session-disk readiness with exact fixes.

Probe only: never builds, pulls or runs a challenge, and never prints raw engine errors.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.text import Text

from patchground.cli.render import EXIT_ERROR, EXIT_INTERRUPTED, EXIT_OK, emit, emit_error
from patchground.sandbox import EngineProbe, EngineProblem, probe_engine
from patchground.sessions.diagnostics import (
    DiskProbe,
    DiskProblem,
    GitProbe,
    GitProblem,
    probe_disk,
    probe_git,
)


class CheckStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


@dataclass(frozen=True)
class DoctorCheck:
    name: str  # "engine" | "git" | "disk"
    status: CheckStatus
    detail: str
    problem: str | None = None
    fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
            "problem": self.problem,
            "fix": self.fix,
        }


@dataclass(frozen=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]

    @property
    def healthy(self) -> bool:
        return all(check.status is CheckStatus.OK for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {"healthy": self.healthy, "checks": [check.to_dict() for check in self.checks]}


def _platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


_WINDOWS = (
    "Patchground runs on Windows through WSL2: install Docker Desktop with the WSL2 backend, "
    "then run pgnd inside your WSL2 distribution"
)
_ENGINE_FIXES: dict[EngineProblem, dict[str, str]] = {
    EngineProblem.NOT_RUNNING: {
        "macos": "Install and start Docker Desktop (or run `podman machine start` for Podman)",
        "linux": "Install Docker Engine and start it: `sudo systemctl start docker` "
        "(for Podman: `systemctl --user start podman.socket` and set DOCKER_HOST to its socket)",
        "windows": _WINDOWS,
    },
    EngineProblem.PERMISSION: {
        "macos": "Restart Docker Desktop; if it persists, check the socket's owner in "
        "Docker Desktop's settings",
        "linux": "Add yourself to the docker group: `sudo usermod -aG docker $USER`, "
        "then log out and back in",
        "windows": _WINDOWS,
    },
    EngineProblem.TIMEOUT: {
        "macos": "The engine is not answering: restart Docker Desktop and retry",
        "linux": "The engine is not answering: `sudo systemctl restart docker` and retry",
        "windows": _WINDOWS,
    },
    EngineProblem.MISCONFIGURED: {
        "macos": "Check DOCKER_HOST and `docker context ls`; unset DOCKER_HOST to use the default",
        "linux": "Check DOCKER_HOST and `docker context ls`; unset DOCKER_HOST to use the default",
        "windows": _WINDOWS,
    },
    EngineProblem.UNHEALTHY: {
        "macos": "The engine returned an error: restart Docker Desktop and retry",
        "linux": "The engine returned an error: `sudo systemctl restart docker` and retry",
        "windows": _WINDOWS,
    },
}
_GIT_FIXES: dict[str, str] = {
    "macos": "Install Git: `xcode-select --install` (or `brew install git`)",
    "linux": "Install Git with your package manager, e.g. `sudo apt install git`",
    "windows": "Install Git inside your WSL2 distribution, e.g. `sudo apt install git`",
}


def _gib(value: int) -> str:
    return f"{value / 1024**3:.1f} GiB"


def engine_check(probe: EngineProbe, platform: str) -> DoctorCheck:
    if probe.reachable:
        version = f" {probe.version}" if probe.version else ""
        api = f" (API {probe.api_version})" if probe.api_version else ""
        return DoctorCheck("engine", CheckStatus.OK, f"{probe.engine or 'Docker'}{version}{api}")
    problem = probe.problem or EngineProblem.UNHEALTHY
    details = {
        EngineProblem.NOT_RUNNING: "container engine not reachable (not installed or not running)",
        EngineProblem.PERMISSION: "permission denied on the container engine socket",
        EngineProblem.TIMEOUT: "container engine did not answer in time",
        EngineProblem.MISCONFIGURED: "container engine connection is misconfigured",
        EngineProblem.UNHEALTHY: "container engine answered with an error",
    }
    return DoctorCheck(
        "engine",
        CheckStatus.FAILED,
        details[problem],
        problem.value,
        _ENGINE_FIXES[problem][platform],
    )


def git_check(probe: GitProbe, platform: str) -> DoctorCheck:
    if probe.available:
        return DoctorCheck("git", CheckStatus.OK, f"git {probe.version}")
    problem = probe.problem or GitProblem.UNUSABLE
    if problem is GitProblem.MISSING:
        return DoctorCheck(
            "git", CheckStatus.FAILED, "git not found on PATH", problem.value, _GIT_FIXES[platform]
        )
    return DoctorCheck(
        "git",
        CheckStatus.FAILED,
        "git was found but `git --version` failed",
        problem.value,
        "Reinstall Git, then check that `git --version` works in a new terminal",
    )


def disk_check(probe: DiskProbe) -> DoctorCheck:
    minimum = _gib(probe.minimum_bytes)
    if probe.ok and probe.free_bytes is not None:
        return DoctorCheck(
            "disk",
            CheckStatus.OK,
            f"{_gib(probe.free_bytes)} free for sessions at {probe.location} "
            f"(baseline {minimum}; images may need more)",
        )
    problem = probe.problem or DiskProblem.UNREADABLE
    if problem is DiskProblem.LOW_SPACE and probe.free_bytes is not None:
        return DoctorCheck(
            "disk",
            CheckStatus.FAILED,
            f"only {_gib(probe.free_bytes)} free at {probe.location}; baseline is {minimum}",
            problem.value,
            f"Free at least {minimum} on the disk holding {probe.location}; "
            "review files before deleting them",
        )
    if problem is DiskProblem.NOT_WRITABLE:
        return DoctorCheck(
            "disk",
            CheckStatus.FAILED,
            f"cannot create sessions at {probe.location}",
            problem.value,
            f"Make {probe.location} (or its nearest existing parent) a writable directory",
        )
    return DoctorCheck(
        "disk",
        CheckStatus.FAILED,
        f"cannot inspect the disk at {probe.location}",
        problem.value,
        f"Check that {probe.location} or a parent directory exists and is readable",
    )


def run_doctor() -> DoctorReport:
    """Assemble every check; each probe reports its own failure instead of raising."""
    platform = _platform()
    return DoctorReport(
        (
            engine_check(probe_engine(), platform),
            git_check(probe_git(), platform),
            disk_check(probe_disk()),
        )
    )


_MARKS = {CheckStatus.OK: ("✓", "green"), CheckStatus.FAILED: ("✗", "red")}


def _human(console: Console, report: DoctorReport) -> None:
    width = max(len(check.name) for check in report.checks)
    for check in report.checks:
        mark, style = _MARKS[check.status]
        line = Text()
        line.append(f"{mark} ", style=style)
        line.append(check.name.ljust(width), style="bold")
        line.append(f"  {check.detail}")
        console.print(line)
        if check.fix:
            console.print(Text(f"    fix: {check.fix}"))
    if report.healthy:
        console.print(Text("ready", style="bold green"))
    else:
        failed = sum(check.status is CheckStatus.FAILED for check in report.checks)
        console.print(Text(f"not ready: {failed} check(s) failed", style="bold red"))


def doctor(
    json_mode: Annotated[
        bool, typer.Option("--json", help="Print one JSON document on stdout.")
    ] = False,
) -> None:
    """Check the container engine, Git and disk space, and print the exact fix for each failure."""
    try:
        report = run_doctor()
    except KeyboardInterrupt as exc:
        emit_error("interrupted", "interrupted", json_mode)
        raise typer.Exit(EXIT_INTERRUPTED) from exc
    except Exception as exc:  # never a traceback or raw message; still one JSON document
        emit_error("internal", f"doctor failed unexpectedly ({type(exc).__name__})", json_mode)
        raise typer.Exit(EXIT_ERROR) from exc
    emit(report.to_dict(), lambda console: _human(console, report), json_mode)
    raise typer.Exit(EXIT_OK if report.healthy else EXIT_ERROR)
