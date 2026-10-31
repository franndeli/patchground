"""Real Docker session loop; edits only user code, never reads the private checks or solution."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from patchground.cli.app import app
from patchground.sessions import check_session, reset_session, session_status, start_session

pytestmark = pytest.mark.docker
EXAMPLE = Path(__file__).resolve().parents[2] / "examples/pagination-last-page"


def authored_copy(destination: Path) -> None:
    # Sessions require the authored layout, but never consume a reference solution.
    shutil.copytree(
        EXAMPLE, destination, ignore=shutil.ignore_patterns("solution", "verification.json")
    )
    (destination / "solution").mkdir()
    (destination / "solution/reference.patch").touch()


def git_state(workspace: Path) -> dict[str, bytes]:
    git = workspace / ".git"
    return {p.relative_to(git).as_posix(): p.read_bytes() for p in git.rglob("*") if p.is_file()}


def fix_pagination(workspace: Path) -> None:
    code = workspace / "src/catalog/pagination.py"
    original = code.read_text()
    broken = "max(1, len(items) // per_page)"
    assert broken in original
    code.write_text(original.replace(broken, "max(1, (len(items) + per_page - 1) // per_page)"))


def test_session_loop(tmp_path: Path) -> None:
    source = tmp_path / EXAMPLE.name
    authored_copy(source)
    root = tmp_path / "sessions"
    started = start_session(source, root=root)
    before = git_state(started.workspace)
    shutil.rmtree(source)
    broken = check_session(started.session, root=root)
    assert not broken.passed
    assert broken.counts["failed"] > 0
    assert git_state(started.workspace) == before
    fix_pagination(started.workspace)
    fixed = check_session(started.workspace, root=root)
    assert fixed.passed
    assert git_state(started.workspace) == before
    assert session_status(started.session, root=root).last_check == fixed
    assert not list(started.workspace.rglob("reference.patch"))
    assert "log_tail" not in fixed.model_dump_json()
    reset_session(started.workspace, root=root)
    assert git_state(started.workspace) == before
    assert not check_session(started.workspace, root=root).passed


def test_cli_session_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    source = tmp_path / EXAMPLE.name
    authored_copy(source)
    runner = CliRunner()
    start = runner.invoke(app, ["start", str(source), "--no-timer", "--json"])
    assert start.exit_code == 0
    doc = json.loads(start.stdout)
    session = Path(doc["session"])
    workspace = Path(doc["workspace"])
    assert session.parent == tmp_path / "patchground/sessions"
    before = git_state(workspace)
    shutil.rmtree(source)
    check = runner.invoke(app, ["check", "--session", str(session), "--json"])
    assert check.exit_code == 1
    assert json.loads(check.stdout)["passed"] is False
    fix_pagination(workspace)
    monkeypatch.chdir(workspace)
    check = runner.invoke(app, ["check", "--json"])
    assert check.exit_code == 0
    assert json.loads(check.stdout)["passed"] is True
    status = runner.invoke(app, ["status", "--json"])
    assert status.exit_code == 0
    assert json.loads(status.stdout)["last_check"]["passed"] is True
    reset = runner.invoke(app, ["reset", "--yes", "--json"])
    assert reset.exit_code == 0
    assert json.loads(reset.stdout)["challenge_id"] == EXAMPLE.name
    check = runner.invoke(app, ["check", "--json"])
    assert check.exit_code == 1
    assert git_state(workspace) == before
