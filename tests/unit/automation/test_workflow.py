"""Real committed Git snapshots, with injected execution and no Docker."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from patchground.automation import validate_changes
from patchground.sandbox import (
    BuildFailed,
    BuildResult,
    EngineUnavailable,
    Limits,
    RunOutcome,
    RunResult,
    TestResult,
    TestStatus,
)

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "pagination-last-page"


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(root: Path) -> str:
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@users.noreply.github.com",
        "commit",
        "-qm",
        "fixture",
    )
    return git(root, "rev-parse", "HEAD")


def test_challenge_at_checkout_root_preserves_folder_identity(tmp_path: Path) -> None:
    add(tmp_path, "root-exercise")
    source = tmp_path / "root-exercise"
    git(source, "init", "-q")
    head = commit(source)
    result = validate_changes(source, consent=True, sandbox=Sandbox())
    assert result.exit_code == 0
    assert result.selected == ["."]
    assert not (source / "verification.json").exists()
    skipped = validate_changes(source, base=head)
    assert skipped.exit_code == 0
    assert skipped.unchanged == ["."]
    assert skipped.to_dict()["status"] == "skipped"


def add(root: Path, name: str) -> None:
    shutil.copytree(EXAMPLE, root / name)
    manifest = root / name / "challenge.yaml"
    manifest.write_text(
        manifest.read_text()
        .replace("id: pagination-last-page", f"id: {name}")
        .replace("pytest -q -p no:cacheprovider --junitxml=$PG_RESULTS/junit.xml", "custom-runner")
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    add(tmp_path, "a")
    commit(tmp_path)
    return tmp_path


class Sandbox:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.builds = 0
        self.runs = 0
        self.dockerfiles: list[str] = []

    def build_image(self, dockerfile: Path, *, name: str) -> BuildResult:
        self.builds += 1
        self.dockerfiles.append(dockerfile.read_text())
        if self.error:
            raise self.error
        return BuildResult(image_id="sha256:fake", tag="fixture", log="private build log")

    def run_check(
        self, image_id: str, layers: Sequence[Path], command: str, *, limits: Limits
    ) -> RunResult:
        kind = self.runs % 9
        self.runs += 1
        tests = [
            TestResult(id="visible", name="visible", classname="tests", status=TestStatus.PASSED)
        ]
        if kind not in (0, 3, 6):
            tests.append(
                TestResult(
                    id="hidden",
                    name="hidden",
                    classname="tests",
                    status=TestStatus.FAILED if kind in (1, 4, 7) else TestStatus.PASSED,
                )
            )
        outcome = RunOutcome.FAILED if kind in (1, 4, 7) else RunOutcome.PASSED
        return RunResult(outcome, tuple(tests), 0, None, "private hidden source log")


def test_committed_input_and_safe_success(repo: Path) -> None:
    before = git(repo, "rev-parse", "HEAD")
    original = (repo / "a/environment/Dockerfile").read_text()
    (repo / "a/environment/Dockerfile").write_text("dirty checkout must not execute")
    git(repo, "add", "a/environment/Dockerfile")
    state = git(repo, "status", "--porcelain")
    box = Sandbox()
    result = validate_changes(repo, consent=True, sandbox=box)
    assert result.exit_code == 0
    assert box.dockerfiles == [original]
    assert result.commit == before
    assert git(repo, "status", "--porcelain") == state
    assert git(repo, "rev-parse", "HEAD") == before
    data = json.dumps(result.to_dict())
    assert str(repo) not in data
    assert "private" not in data
    assert "patchground-source-" not in data
    assert result.validations[0]["steps"][-1]["status"] == "not_run"
    assert not (repo / "a/verification.json").exists()


def test_selection_new_changed_removed_and_unchanged(repo: Path) -> None:
    add(repo, "b")
    add(repo, "c")
    base = commit(repo)
    shutil.rmtree(repo / "b")
    (repo / "a/TICKET.md").write_text("Changed ticket")
    add(repo, "d")
    commit(repo)
    result = validate_changes(repo, base=base, consent=True, sandbox=Sandbox())
    assert result.exit_code == 0
    assert result.selected == ["a", "d"]
    assert result.unchanged == ["c"]
    assert result.removed == ["b"]
    assert result.base_commit == base


def test_no_change_skips_without_consent(repo: Path) -> None:
    box = Sandbox()
    result = validate_changes(repo, base="HEAD", sandbox=box)
    assert result.exit_code == 0
    assert result.to_dict()["status"] == "skipped"
    assert result.unchanged == ["a"]
    assert box.builds == 0


@pytest.mark.parametrize("base", [None, "missing-base", "--unsafe"])
def test_consent_before_build_and_conservative_fallback(repo: Path, base: str | None) -> None:
    box = Sandbox()
    result = validate_changes(repo, base=base, sandbox=box)
    assert result.exit_code == 2
    assert result.selected == ["a"]
    assert result.selection_mode == ("all" if base is None else "fallback_all")
    assert box.builds == 0


def test_malformed_candidate_preflight(repo: Path) -> None:
    add(repo, "z")
    (repo / "z/challenge.yaml").write_text("not: [valid")
    commit(repo)
    box = Sandbox()
    result = validate_changes(repo, consent=True, sandbox=box)
    assert result.exit_code == 1
    assert box.builds == 0
    assert "valid" in result.errors[0]


@pytest.mark.parametrize(
    "error,code",
    [
        (BuildFailed("private source and credentials"), 1),
        (EngineUnavailable("private scratch path"), 2),
    ],
)
def test_failures_are_safe(repo: Path, error: Exception, code: int) -> None:
    result = validate_changes(repo, consent=True, sandbox=Sandbox(error))
    assert result.exit_code == code
    assert "private" not in json.dumps(result.to_dict())


def test_pack_metadata_change_selects_all(repo: Path) -> None:
    metadata = repo / "pack.yaml"
    metadata.write_text(
        'spec_version: "0.1"\nname: fixture\nversion: 1.0.0\ndescription: Before\nchallenges: [a]\n'
    )
    base = commit(repo)
    metadata.write_text(metadata.read_text().replace("Before", "After"))
    commit(repo)
    result = validate_changes(repo, base=base)
    assert result.selected == ["a"]
    assert result.unchanged == []


@pytest.mark.parametrize("directory", ["../outside", "/absolute", "missing"])
def test_invalid_directory(repo: Path, directory: str) -> None:
    assert validate_changes(repo, directory=directory).exit_code != 0


def test_empty_directory(repo: Path) -> None:
    (repo / "empty").mkdir()
    (repo / "empty/file").write_text("not a challenge")
    commit(repo)
    assert validate_changes(repo, directory="empty").exit_code == 1


def test_challenge_root_and_unavailable_base(repo: Path) -> None:
    result = validate_changes(repo, directory="a", base="absent", consent=True, sandbox=Sandbox())
    assert result.exit_code == 0
    assert result.selected == ["a"]
    assert result.selection_mode == "fallback_all"


def test_indexed_pack_ignores_unindexed_invalid_candidate(repo: Path) -> None:
    (repo / "pack.yaml").write_text(
        'spec_version: "0.1"\nname: fixture\nversion: 1.0.0\n'
        "description: Fixture\nchallenges: [a]\n"
    )
    add(repo, "unindexed")
    (repo / "unindexed/challenge.yaml").write_text("invalid")
    commit(repo)
    result = validate_changes(repo, consent=True, sandbox=Sandbox())
    assert result.exit_code == 0
    assert result.selected == ["a"]


def test_invalid_indexed_manifest_has_relative_file_line(repo: Path) -> None:
    (repo / "a/challenge.yaml").write_text("not: [valid")
    commit(repo)
    result = validate_changes(repo, directory="a", consent=True, sandbox=Sandbox())
    assert result.exit_code == 1
    assert result.errors[0].startswith("a/challenge.yaml:1:")
    assert str(repo) not in json.dumps(result.to_dict())


def test_source_configuration_cannot_execute(repo: Path) -> None:
    marker = repo / "executed"
    script = repo / "untracked-script"
    script.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
    script.chmod(0o755)
    git(repo, "config", "core.fsmonitor", str(script))
    result = validate_changes(repo, base="HEAD")
    assert result.exit_code == 0
    assert not marker.exists()


def test_verifier_excludes_original_and_entire_captured_source(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from patchground import verify

    original = verify.validate_challenge
    forwarded: list[tuple[Path, ...]] = []

    def validate(
        folder: Path,
        *,
        write: bool,
        sandbox: verify.Sandbox | None,
        input_roots: tuple[Path, ...] = (),
    ) -> verify.ValidationReport:
        assert input_roots == (repo.resolve(), folder.parent)
        forwarded.append(input_roots)
        assert folder.parent != repo.resolve()
        assert (folder.parent / "a/challenge.yaml").is_file()
        return original(folder, write=write, sandbox=sandbox, input_roots=input_roots)

    monkeypatch.setattr(verify, "validate_challenge", validate)
    result = validate_changes(repo, consent=True, sandbox=Sandbox())
    assert result.exit_code == 0
    assert len(forwarded) == 1


def test_executable_mode_change_selects_challenge(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "update-index", "--chmod=+x", "a/environment/Dockerfile")
    git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@users.noreply.github.com",
        "commit",
        "-qm",
        "fixture executable flag",
    )
    result = validate_changes(repo, base=base)
    assert result.selected == ["a"]
    assert result.unchanged == []
    assert result.exit_code == 2  # The selected committed change still requires consent.
