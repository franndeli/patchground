"""Resource-limit labels require engine evidence, never an exit-code guess."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import pytest
from docker.errors import NotFound

from patchground.sandbox import Limits, RunOutcome
from patchground.sandbox import run as sandbox_run


@pytest.mark.parametrize("check", [False, True], ids=["command", "check"])
@pytest.mark.parametrize(
    ("exit_code", "oom_killed", "expected"),
    [(137, False, None), (137, True, "memory"), (None, True, "timeout")],
)
def test_limit_requires_engine_evidence(
    monkeypatch: pytest.MonkeyPatch,
    check: bool,
    exit_code: int | None,
    oom_killed: bool,
    expected: str | None,
) -> None:
    class Container:
        def __init__(self) -> None:
            self.attrs: dict[str, Any] = {}

        def start(self) -> None:
            pass

        def reload(self) -> None:
            # Only reload supplies the authoritative engine state.
            self.attrs = {"State": {"OOMKilled": oom_killed}}

        def logs(self, **_: Any) -> bytes:
            return b""

        def get_archive(self, _: str) -> None:
            raise NotFound("no JUnit")

    container = Container()

    @contextlib.contextmanager
    def hardened(*_: Any, **__: Any) -> Iterator[Container]:
        yield container

    monkeypatch.setattr(sandbox_run, "_hardened_container", hardened)
    monkeypatch.setattr(sandbox_run, "_wait", lambda *_: exit_code)
    monkeypatch.setattr(sandbox_run, "_output_tail", lambda _: "")
    # A non-OOM check still has to derive its outcome from JUnit, not exit 137.
    if check:
        result = sandbox_run.run_check("image", [], "true", limits=Limits())
        assert result.outcome is (
            RunOutcome.LIMIT_EXCEEDED if expected else RunOutcome.MISSING_RESULTS
        )
    else:
        result = sandbox_run.run_command("image", [], ["true"], limits=Limits())
    assert result.exit_code == exit_code
    assert result.limit == expected
