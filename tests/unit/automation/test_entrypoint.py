from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from patchground.automation.__main__ import main


class FakeResult:
    def __init__(self, exit_code: int = 0, document: dict[str, Any] | None = None) -> None:
        self.exit_code = exit_code
        self._document = document or {"format": "fake", "version": 1}

    def to_dict(self) -> dict[str, Any]:
        return self._document


class Recorder:
    def __init__(self, result: FakeResult | BaseException) -> None:
        self.result = result
        self.calls: list[tuple[Path, dict[str, Any]]] = []

    def __call__(self, source: Path, **kwargs: Any) -> FakeResult:
        self.calls.append((source, kwargs))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "checkout"
    out = tmp_path / "out"
    source.mkdir()
    out.mkdir()
    return source, out


def run(source: Path, report: Path, validate: Recorder, *extra: str) -> int:
    argv = ["--source", str(source), "--report", str(report), *extra]
    return main(argv, validate=validate)


def test_success_writes_report_and_passes_arguments(dirs: tuple[Path, Path]) -> None:
    source, out = dirs
    fake = Recorder(FakeResult(0, {"format": "x", "version": 1}))
    code = run(
        source, out / "r.json", fake, "--directory", "packs", "--base", "abc1234", "--consent"
    )
    assert code == 0
    assert json.loads((out / "r.json").read_text()) == {"format": "x", "version": 1}
    assert fake.calls == [
        (source.resolve(), {"directory": "packs", "base": "abc1234", "consent": True})
    ]


def test_consent_and_base_default_off(dirs: tuple[Path, Path]) -> None:
    source, out = dirs
    fake = Recorder(FakeResult())
    run(source, out / "r.json", fake)
    assert fake.calls[0][1] == {"directory": ".", "base": None, "consent": False}


def test_validation_failure_exit_code_keeps_report(dirs: tuple[Path, Path]) -> None:
    source, out = dirs
    code = run(source, out / "r.json", Recorder(FakeResult(1)))
    assert code == 1
    assert (out / "r.json").exists()


def test_report_inside_source_refused(dirs: tuple[Path, Path]) -> None:
    source, _ = dirs
    fake = Recorder(FakeResult())
    assert run(source, source / "r.json", fake) == 2
    assert not (source / "r.json").exists()
    assert fake.calls == []


def test_existing_report_not_overwritten(dirs: tuple[Path, Path]) -> None:
    source, out = dirs
    (out / "r.json").write_text("keep")
    fake = Recorder(FakeResult())
    assert run(source, out / "r.json", fake) == 2
    assert (out / "r.json").read_text() == "keep"
    assert fake.calls == []


def test_symlink_report_not_followed(dirs: tuple[Path, Path]) -> None:
    source, out = dirs
    target = out / "target"
    (out / "link.json").symlink_to(target)
    assert run(source, out / "link.json", Recorder(FakeResult())) == 2
    assert not target.exists()


def test_missing_report_dir_and_source(dirs: tuple[Path, Path]) -> None:
    source, out = dirs
    assert run(source, out / "nope" / "r.json", Recorder(FakeResult())) == 2
    assert run(out / "missing", out / "r.json", Recorder(FakeResult())) == 2
    assert not (out / "r.json").exists()


def test_exception_yields_safe_error_report(
    dirs: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    source, out = dirs
    private_message = "/private/fixture/source sk-test-not-a-real-key"
    code = run(source, out / "r.json", Recorder(RuntimeError(private_message)))
    assert code == 2
    text = (out / "r.json").read_text() + capsys.readouterr().err
    assert "RuntimeError" in text
    assert private_message not in text and "/private/fixture/" not in text
    assert json.loads((out / "r.json").read_text())["format"] == "patchground-automation-error"


def test_usage_error_is_json_not_argparse_text(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--bogus"], validate=Recorder(FakeResult())) == 2
    err = capsys.readouterr().err
    assert json.loads(err)["format"] == "patchground-automation-error"


def test_isolated_mode_ignores_cwd_and_pythonpath(tmp_path: Path) -> None:
    evil = tmp_path / "evil"
    evil.mkdir()
    (evil / "json.py").write_text("raise SystemExit(99)\n")
    env = {**os.environ, "PYTHONPATH": str(evil)}
    done = subprocess.run(
        [sys.executable, "-I", "-m", "patchground.automation", "--bogus"],
        cwd=evil,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2
    assert "patchground-automation-error" in done.stderr


def test_symlinked_report_ancestor_refused(dirs: tuple[Path, Path], tmp_path: Path) -> None:
    source, _ = dirs
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "alias").symlink_to(real)
    fake = Recorder(FakeResult())
    assert run(source, tmp_path / "alias" / "r.json", fake) == 2
    assert list(real.iterdir()) == [] and fake.calls == []


def test_dotdot_report_path_refused(dirs: tuple[Path, Path]) -> None:
    source, _ = dirs
    (source / "sub").mkdir()
    fake = Recorder(FakeResult())
    assert run(source, source / "sub" / ".." / ".." / "out" / "r.json", fake) == 2
    assert fake.calls == []


def test_interrupt_writes_cancellation_and_closes_descriptor(
    dirs: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    source, out = dirs
    before = set(Path("/dev/fd").iterdir())
    code = run(source, out / "r.json", Recorder(KeyboardInterrupt()))
    assert code == 130
    report = json.loads((out / "r.json").read_text())
    assert report["error"] == "cancelled" and report["exit_code"] == 130
    err = capsys.readouterr().err
    assert "Traceback" not in err and json.loads(err)["error"] == "cancelled"
    assert set(Path("/dev/fd").iterdir()) <= before


def test_unwritable_report_dir_is_safe_usage_error(
    dirs: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    source, out = dirs
    out.chmod(0o500)
    try:
        if os.access(out, os.W_OK):
            pytest.skip("directory permissions not enforced")
        assert run(source, out / "r.json", Recorder(FakeResult())) == 2
    finally:
        out.chmod(0o700)
    assert str(out) not in capsys.readouterr().err
