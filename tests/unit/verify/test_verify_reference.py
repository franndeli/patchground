"""Unit tests for applying reference.patch with host git."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest

from patchground.verify.errors import VerifyEnvironmentError
from patchground.verify.reference import PatchError, apply_patch, copy_workspace, snapshot

PATCH = (
    "diff --git a/app.txt b/app.txt\n--- a/app.txt\n+++ b/app.txt\n@@ -1 +1 @@\n-broken\n+fixed\n"
)


def make_workspace(temp_root: Path) -> Path:
    workspace = temp_root / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "app.txt").write_text("broken\n")
    return workspace


def test_apply_patch_edits_target(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path / "t")
    patch = tmp_path / "reference.patch"
    patch.write_text(PATCH)
    before = snapshot(workspace)
    apply_patch(patch, workspace, tmp_path / "t")
    assert (workspace / "app.txt").read_text() == "fixed\n"
    assert snapshot(workspace) != before


def test_enclosing_repository_is_not_discovered(tmp_path: Path) -> None:
    # If git found the enclosing repo, it would resolve patch paths from the repo root and the
    # patch (relative to the workspace) would not apply.
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    temp_root = repo / "t"
    workspace = make_workspace(temp_root)
    patch = tmp_path / "reference.patch"
    patch.write_text(PATCH)
    apply_patch(patch, workspace, temp_root)
    assert (workspace / "app.txt").read_text() == "fixed\n"
    listed = subprocess.run(
        ["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True
    )
    assert listed.stdout == ""  # index untouched


def test_check_failure_is_sanitized_and_changes_nothing(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path / "t")
    (workspace / "app.txt").write_text("something else\n")
    patch = tmp_path / "reference.patch"
    patch.write_text(PATCH)
    before = snapshot(workspace)
    with pytest.raises(PatchError) as info:
        apply_patch(patch, workspace, tmp_path / "t")
    assert info.value.stderr == "git apply exited 1"
    assert "app.txt" not in str(info.value)
    assert snapshot(workspace) == before


def test_snapshot_tracks_paths_and_content(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.txt").write_text("1")
    first = snapshot(tmp_path)
    assert set(first) == {"a/x.txt"}
    (tmp_path / "a" / "x.txt").write_text("2")
    assert snapshot(tmp_path) != first
    (tmp_path / "link").symlink_to("a")
    assert "link" in snapshot(tmp_path)


# --------------------------------------------------------------------------------------------------
# A challenge-controlled .git must never make host git run commands
# --------------------------------------------------------------------------------------------------


def plant_git_filter(workspace: Path, marker: Path) -> None:
    """Turn ``workspace`` into a repo whose clean/smudge filter touches ``marker`` on the host."""
    command = f"touch {shlex.quote(str(marker))}; cat"
    subprocess.run(["git", "init", "-q", str(workspace)], check=True, capture_output=True)
    for key in ("filter.x.clean", "filter.x.smudge"):
        subprocess.run(["git", "-C", str(workspace), "config", key, command], check=True)
    (workspace / ".gitattributes").write_text("* filter=x\n")


def test_planted_filter_runs_with_plain_git_apply(tmp_path: Path) -> None:
    # Control: proves the fixture is a real attack, so the next test is not vacuous.
    workspace = make_workspace(tmp_path / "t")
    marker = tmp_path / "pwned"
    plant_git_filter(workspace, marker)
    patch = tmp_path / "reference.patch"
    patch.write_text(PATCH)
    subprocess.run(
        ["git", "apply", "-p1", str(patch)], cwd=workspace, check=True, capture_output=True
    )
    assert marker.exists()


def test_apply_patch_ignores_a_git_repository_inside_the_target(tmp_path: Path) -> None:
    temp_root = tmp_path / "t"
    workspace = make_workspace(temp_root)
    marker = tmp_path / "pwned"
    plant_git_filter(workspace, marker)
    patch = tmp_path / "reference.patch"
    patch.write_text(PATCH)

    apply_patch(patch, workspace, temp_root)

    assert (workspace / "app.txt").read_text() == "fixed\n"
    assert not marker.exists()


def test_gitattributes_without_a_repository_is_harmless(tmp_path: Path) -> None:
    temp_root = tmp_path / "t"
    workspace = make_workspace(temp_root)
    (workspace / ".gitattributes").write_text("* filter=x diff=x merge=x\n")
    patch = tmp_path / "reference.patch"
    patch.write_text(PATCH)
    apply_patch(patch, workspace, temp_root)
    assert (workspace / "app.txt").read_text() == "fixed\n"


def test_copy_workspace_drops_git_entries_in_any_case_and_depth(tmp_path: Path) -> None:
    source = tmp_path / "workspace"
    marker = tmp_path / "pwned"
    make_workspace(tmp_path)
    plant_git_filter(source, marker)
    (source / "sub" / ".GIT").mkdir(parents=True)
    (source / "sub" / ".GIT" / "config").write_text("[core]\n")
    (source / "deep" / "er").mkdir(parents=True)
    (source / "deep" / "er" / ".git").write_text("gitdir: /elsewhere\n")
    (source / "sub" / "keep.git").write_text("not a git entry\n")

    copy = tmp_path / "t" / "workspace"
    copy_workspace(source, copy)

    assert set(snapshot(copy)) == {"app.txt", ".gitattributes", "sub/keep.git"}
    patch = tmp_path / "reference.patch"
    patch.write_text(PATCH)
    apply_patch(patch, copy, tmp_path / "t")
    assert not marker.exists()


def test_copy_workspace_failure_is_an_environment_error(tmp_path: Path) -> None:
    with pytest.raises(VerifyEnvironmentError, match="could not copy the workspace"):
        copy_workspace(tmp_path / "missing", tmp_path / "copy")
