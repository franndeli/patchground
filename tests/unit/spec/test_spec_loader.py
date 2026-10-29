"""Unit tests for loading challenge and pack folders."""

from __future__ import annotations

import os
import socket
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from patchground.spec import (
    AIPolicy,
    ChallengeType,
    Difficulty,
    ManifestError,
    ManifestIssue,
    Provenance,
    load_challenge,
    load_pack,
)

VALID_CHALLENGE_YAML = """\
spec_version: "0.1"
id: duplicate-charges-on-retry
version: 1.0.0
title: Duplicate charges after a payment retry
type: debug
summary: A retry path charges customers twice. Find the root cause and fix it with a test.
languages: [python]
tags: [idempotency, retries]
difficulty: intermediate
timebox_minutes: 45
ai_policy: allowed
environment:
  dockerfile: environment/Dockerfile
  services: []
  test_command: pytest -q --junitxml=$PG_RESULTS/junit.xml
checks:
  visible: checks/visible
  hidden: checks/hidden
solution: solution/reference.patch
expected_paths: [src/payments/]
hints:
  - Look at what happens when the provider times out but the charge succeeded.
debrief:
  questions: debrief/questions.md
  focus: [debugging_method, test_quality, scope_judgment]
author: {name: Test Author, github: test-author}
content_license: CC-BY-4.0
provenance: handmade
"""

DEFAULT_FILES: dict[str, str] = {
    "TICKET.md": "# Ticket\n",
    "workspace/src/payments/charge.py": "def charge():\n    pass\n",
    "environment/Dockerfile": "FROM python:3.12-slim\n",
    "checks/visible/tests/test_visible.py": "def test_visible():\n    pass\n",
    "checks/hidden/tests/test_hidden.py": "SECRET_HIDDEN_CONTENT = 1\n",
    "solution/reference.patch": "--- a\n+++ b\n",
    "debrief/questions.md": "- Why?\n",
}

ChallengeFactory = Callable[..., Path]


def write_files(root: Path, files: dict[str, str | None]) -> None:
    for rel, content in files.items():
        path = root / rel
        if content is None:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.fixture
def make_challenge(tmp_path: Path) -> ChallengeFactory:
    """Build a challenge folder; ``files`` entries override defaults (``None`` removes one)."""

    def factory(
        manifest: str | None = VALID_CHALLENGE_YAML,
        *,
        name: str = "duplicate-charges-on-retry",
        files: dict[str, str | None] | None = None,
        parent: Path | None = None,
    ) -> Path:
        root = (parent or tmp_path) / name
        root.mkdir(parents=True)
        merged: dict[str, str | None] = {**DEFAULT_FILES, **(files or {})}
        write_files(root, merged)
        if manifest is not None:
            (root / "challenge.yaml").write_text(manifest, encoding="utf-8")
        return root

    return factory


def issues_of(folder: Path, loader: object = load_challenge) -> list[ManifestIssue]:
    assert callable(loader)
    with pytest.raises(ManifestError) as info:
        loader(folder)
    return info.value.issues


def line_of(text: str, needle: str) -> int:
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} not in manifest")


def replace(old: str, new: str, text: str = VALID_CHALLENGE_YAML) -> str:
    assert old in text
    return text.replace(old, new, 1)


# --- valid manifests --------------------------------------------------------------------------


def test_valid_full_manifest(make_challenge: ChallengeFactory) -> None:
    folder = make_challenge()
    challenge = load_challenge(folder)
    m = challenge.manifest
    assert challenge.root == folder.resolve()
    assert challenge.manifest_path == folder.resolve() / "challenge.yaml"
    assert m.id == "duplicate-charges-on-retry"
    assert m.type is ChallengeType.DEBUG
    assert m.difficulty is Difficulty.INTERMEDIATE
    assert m.ai_policy is AIPolicy.ALLOWED
    assert m.provenance is Provenance.HANDMADE
    assert m.environment.dockerfile == "environment/Dockerfile"
    assert m.checks.hidden == "checks/hidden"
    assert m.debrief is not None and m.debrief.focus[0] == "debugging_method"
    assert m.author.github == "test-author"
    assert m.timebox_minutes == 45
    assert type(m.title) is str


def test_minimal_manifest_defaults(make_challenge: ChallengeFactory) -> None:
    manifest = """\
spec_version: "0.1"
id: minimal
version: 0.1.0-rc.1+build.5
title: Minimal
type: feature
summary: Smallest valid challenge.
languages: [go]
difficulty: beginner
timebox_minutes: 10
ai_policy: forbidden
environment: {dockerfile: environment/Dockerfile, test_command: go test ./...}
checks: {hidden: checks/hidden}
solution: solution/reference.patch
author: {name: Someone}
"""
    m = load_challenge(make_challenge(manifest, name="minimal")).manifest
    assert m.content_license == "CC-BY-4.0"
    assert m.provenance is Provenance.HANDMADE
    assert m.checks.visible is None
    assert m.debrief is None
    assert m.tags == [] and m.hints == [] and m.expected_paths == []
    assert m.environment.services == []
    assert m.author.github is None


def test_extension_keys_accepted_at_root_and_nested(make_challenge: ChallengeFactory) -> None:
    manifest = (
        VALID_CHALLENGE_YAML.replace(
            "environment:\n", "environment:\n  x-cpu: 2\n  x-notes: {any: [thing]}\n"
        )
        .replace("checks:\n", "checks:\n  x-flaky: true\n")
        .replace("debrief:\n", "debrief:\n  x-extra: 1\n")
        + "x-experiment: {deep: {unknown: keys}}\n"
    )
    manifest = manifest.replace(
        "author: {name: Test Author, github: test-author}",
        "author: {name: Test Author, github: test-author, x-mastodon: '@a'}",
    )
    m = load_challenge(make_challenge(manifest)).manifest
    assert m.environment.test_command.startswith("pytest")
    assert "x-experiment" not in m.model_dump()


# --- schema problems with lines ----------------------------------------------------------------


def test_unknown_key_rejected_with_line(make_challenge: ChallengeFactory) -> None:
    manifest = replace("  services: []\n", "  services: []\n  network: host\n")
    issues = issues_of(make_challenge(manifest))
    assert len(issues) == 1
    issue = issues[0]
    assert issue.field == "environment.network"
    assert issue.line == line_of(manifest, "network: host")
    assert "unknown key" in issue.message
    assert issue.file.name == "challenge.yaml"


def test_multiple_errors_reported_together(make_challenge: ChallengeFactory) -> None:
    manifest = replace("  test_command: pytest -q --junitxml=$PG_RESULTS/junit.xml\n", "")
    manifest = replace("timebox_minutes: 45", "timebox_minutes: -5", manifest)
    manifest = replace("difficulty: intermediate", "difficulty: expert", manifest)
    manifest = replace("  - Look at", "  - 42\n  - Look at", manifest)
    issues = issues_of(make_challenge(manifest))
    by_field = {issue.field: issue for issue in issues}
    assert set(by_field) == {
        "environment.test_command",
        "timebox_minutes",
        "difficulty",
        "hints[0]",
    }
    # A missing key points at its parent mapping's key.
    assert by_field["environment.test_command"].line == line_of(manifest, "environment:")
    assert by_field["environment.test_command"].message == "field required"
    assert by_field["timebox_minutes"].line == line_of(manifest, "timebox_minutes")
    assert by_field["difficulty"].line == line_of(manifest, "difficulty: expert")
    assert by_field["hints[0]"].line == line_of(manifest, "- 42")
    # Sorted by line.
    lines = [issue.line or 0 for issue in issues]
    assert lines == sorted(lines)


def test_issue_formatting(make_challenge: ChallengeFactory, tmp_path: Path) -> None:
    manifest = replace("  test_command: pytest -q --junitxml=$PG_RESULTS/junit.xml\n", "")
    folder = make_challenge(manifest)
    (issue,) = issues_of(folder)
    line = line_of(manifest, "environment:")
    assert (
        issue.format(folder) == f"challenge.yaml:{line}: environment.test_command: field required"
    )
    assert issue.format(tmp_path) == (
        f"duplicate-charges-on-retry/challenge.yaml:{line}: "
        "environment.test_command: field required"
    )
    assert (
        str(issue)
        == f"{folder / 'challenge.yaml'}:{line}: environment.test_command: field required"
    )
    assert ManifestIssue(Path("a.yaml"), None, None, "boom").format() == "a.yaml: boom"


def test_string_number_is_not_coerced(make_challenge: ChallengeFactory) -> None:
    manifest = replace("timebox_minutes: 45", 'timebox_minutes: "45"')
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == "timebox_minutes"


def test_unquoted_spec_version_rejected(make_challenge: ChallengeFactory) -> None:
    manifest = replace('spec_version: "0.1"', "spec_version: 0.1")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == "spec_version"
    assert issue.line == 1
    assert 'quote it: spec_version: "0.1"' in issue.message


@pytest.mark.parametrize(
    ("old", "new", "field", "reserved"),
    [
        ("type: debug", "type: incident", "type", "incident"),
        ("type: debug", "type: ai-validation", "type", "ai-validation"),
        ("type: debug", "type: design", "type", "design"),
        ("ai_policy: allowed", "ai_policy: trap", "ai_policy", "trap"),
    ],
)
def test_reserved_values_have_clear_message(
    make_challenge: ChallengeFactory, old: str, new: str, field: str, reserved: str
) -> None:
    manifest = replace(old, new)
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == field
    assert issue.message == f"'{reserved}' is reserved and not part of format v0.1"
    assert issue.line == line_of(manifest, new)


def test_bad_id_and_version_messages(make_challenge: ChallengeFactory) -> None:
    manifest = replace("version: 1.0.0", "version: '1.0'")
    manifest = replace("id: duplicate-charges-on-retry", "id: Bad_Id", manifest)
    issues = issues_of(make_challenge(manifest))
    messages = {(issue.field, issue.message) for issue in issues}
    assert (
        "id",
        "'Bad_Id' is not a kebab-case slug (lowercase letters, digits and single dashes)",
    ) in messages
    assert ("id", "id 'Bad_Id' must match the folder name 'duplicate-charges-on-retry'") in messages
    assert ("version", "'1.0' is not a semantic version (e.g. 1.0.0)") in messages
    assert len(issues) == 3


def test_generated_by_required_when_generated(make_challenge: ChallengeFactory) -> None:
    manifest = replace("provenance: handmade", "provenance: generated")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == "provenance"
    assert "generated_by" in issue.message and "required" in issue.message
    assert issue.line == line_of(manifest, "provenance:")


def test_generated_by_accepted_when_generated(make_challenge: ChallengeFactory) -> None:
    manifest = replace(
        "provenance: handmade",
        "provenance: generated\ngenerated_by: {model: test-model, prompt_version: v1}",
    )
    m = load_challenge(make_challenge(manifest)).manifest
    assert m.generated_by is not None and m.generated_by.prompt_version == "v1"


def test_generated_by_forbidden_when_handmade(make_challenge: ChallengeFactory) -> None:
    manifest = VALID_CHALLENGE_YAML + "generated_by: {model: test-model, prompt_version: v1}\n"
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == "generated_by"
    assert "only allowed" in issue.message
    assert issue.line == line_of(manifest, "generated_by:")


# --- YAML problems ----------------------------------------------------------------------------


def test_duplicate_keys_reported_with_lines(make_challenge: ChallengeFactory) -> None:
    manifest = VALID_CHALLENGE_YAML + "title: Again\nchecks:\n  hidden: checks/hidden\n"
    issues = issues_of(make_challenge(manifest))
    messages = {(issue.line, issue.message) for issue in issues}
    lines = manifest.splitlines()
    assert (len(lines) - 2, "duplicate key 'title' (first defined on line 4)") in messages
    first_checks = line_of(manifest, "checks:")
    assert (len(lines) - 1, f"duplicate key 'checks' (first defined on line {first_checks})") in (
        messages
    )


def test_duplicate_nested_key(make_challenge: ChallengeFactory) -> None:
    manifest = replace("  services: []\n", "  services: []\n  services: [redis]\n")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.line == line_of(manifest, "services: [redis]")
    assert "duplicate key 'services'" in issue.message


def test_yaml_syntax_error_line(make_challenge: ChallengeFactory) -> None:
    manifest = replace("languages: [python]", "languages: [python\nbroken: here")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.message.startswith("YAML error:")
    assert issue.line == line_of(manifest, "broken: here")


def test_root_not_mapping(make_challenge: ChallengeFactory) -> None:
    (issue,) = issues_of(make_challenge("- just\n- a list\n"))
    assert "mapping" in issue.message


def test_non_string_keys(make_challenge: ChallengeFactory) -> None:
    manifest = replace("checks:\n", "checks:\n  1: one\n  null: nothing\n")
    issues = issues_of(make_challenge(manifest))
    assert {(i.line, i.field, i.message) for i in issues} == {
        (line_of(manifest, "1: one"), "checks", "mapping keys must be strings"),
        (line_of(manifest, "null: nothing"), "checks", "mapping keys must be strings"),
    }


def test_empty_manifest(make_challenge: ChallengeFactory) -> None:
    (issue,) = issues_of(make_challenge(""))
    assert "mapping" in issue.message


def test_alias_bomb_is_harmless(make_challenge: ChallengeFactory) -> None:
    bomb = "a: &a [x, x, x, x, x, x, x, x, x]\n"
    for index in range(1, 12):
        bomb += f"x-{index}: &a{index} [" + ", ".join([f"*a{index - 1}" if index > 1 else "*a"] * 9)
        bomb += "]\n"
    issues = issues_of(make_challenge(bomb))
    assert any(issue.field == "a" for issue in issues)


def test_missing_manifest(make_challenge: ChallengeFactory) -> None:
    issues = issues_of(make_challenge(None))
    assert len(issues) == 1
    assert issues[0].message == "challenge.yaml not found"


# --- folder and path problems -----------------------------------------------------------------


def test_id_must_match_folder(make_challenge: ChallengeFactory) -> None:
    (issue,) = issues_of(make_challenge(name="other-name"))
    assert issue.field == "id"
    assert issue.line == 2
    assert "other-name" in issue.message


def test_missing_ticket_and_workspace(make_challenge: ChallengeFactory) -> None:
    folder = make_challenge(files={"TICKET.md": None, "workspace/src/payments/charge.py": None})
    issues = issues_of(folder)
    assert {issue.file.name for issue in issues} == {"TICKET.md", "workspace"}
    assert all("does not exist" in issue.message for issue in issues)


def test_workspace_must_be_directory(make_challenge: ChallengeFactory) -> None:
    folder = make_challenge(files={"workspace/src/payments/charge.py": None, "workspace": "file"})
    (issue,) = issues_of(folder)
    assert issue.file.name == "workspace"
    assert "must be a directory" in issue.message


def test_path_escaping_with_dotdot(make_challenge: ChallengeFactory) -> None:
    manifest = replace("solution: solution/reference.patch", "solution: solution/../../x.patch")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == "solution"
    assert issue.message == "path must stay inside the challenge folder"
    assert issue.line == line_of(manifest, "solution:")


def test_dotdot_that_stays_inside_is_allowed(make_challenge: ChallengeFactory) -> None:
    manifest = replace(
        "solution: solution/reference.patch", "solution: debrief/../solution/reference.patch"
    )
    load_challenge(make_challenge(manifest))


def test_absolute_path_rejected(make_challenge: ChallengeFactory) -> None:
    manifest = replace("  dockerfile: environment/Dockerfile", "  dockerfile: /etc/Dockerfile")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == "environment.dockerfile"
    assert issue.message == "path must be relative to the challenge folder"
    assert issue.line == line_of(manifest, "dockerfile:")


def test_path_escaping_via_symlink(make_challenge: ChallengeFactory, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.patch").write_text("secret", encoding="utf-8")
    folder = make_challenge(files={"solution/reference.patch": None})
    (folder / "solution").mkdir()
    (folder / "solution" / "reference.patch").symlink_to(outside / "x.patch")
    (issue,) = issues_of(folder)
    assert issue.field == "solution"
    assert "outside the challenge folder" in issue.message
    assert "secret" not in issue.message


def test_symlinked_checks_dir_escaping(make_challenge: ChallengeFactory, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    folder = make_challenge(files={"checks/hidden/tests/test_hidden.py": None})
    (folder / "checks" / "hidden").symlink_to(outside, target_is_directory=True)
    (issue,) = issues_of(folder)
    assert issue.field == "checks.hidden"
    assert "outside" in issue.message


def test_missing_and_wrong_kind_references(make_challenge: ChallengeFactory) -> None:
    folder = make_challenge(
        files={
            "debrief/questions.md": None,
            "checks/visible/tests/test_visible.py": None,
            "checks/visible": "now a file",
        }
    )
    issues = issues_of(folder)
    by_field = {issue.field: issue.message for issue in issues}
    assert by_field == {
        "debrief.questions": "'debrief/questions.md' does not exist",
        "checks.visible": "'checks/visible' must be a directory",
    }


def test_dockerfile_must_be_file(make_challenge: ChallengeFactory) -> None:
    manifest = replace("  dockerfile: environment/Dockerfile", "  dockerfile: environment")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.message == "'environment' must be a file"


def test_schema_and_filesystem_problems_reported_together(
    make_challenge: ChallengeFactory,
) -> None:
    manifest = replace("  test_command: pytest -q --junitxml=$PG_RESULTS/junit.xml\n", "")
    folder = make_challenge(manifest, files={"solution/reference.patch": None, "TICKET.md": None})
    issues = issues_of(folder)
    fields = {issue.field for issue in issues}
    assert fields == {"environment.test_command", "solution", None}


def test_check_clash_between_workspace_and_hidden(make_challenge: ChallengeFactory) -> None:
    manifest = VALID_CHALLENGE_YAML
    folder = make_challenge(files={"workspace/tests/test_hidden.py": "x = 1\n"})
    (issue,) = issues_of(folder)
    assert issue.field == "checks.hidden"
    assert issue.line == line_of(manifest, "  hidden:")
    assert "'tests/test_hidden.py'" in issue.message
    assert "workspace/" in issue.message
    assert "SECRET_HIDDEN_CONTENT" not in issue.message


def test_check_clash_between_visible_and_hidden(make_challenge: ChallengeFactory) -> None:
    folder = make_challenge(files={"checks/visible/tests/test_hidden.py": "y = 2\n"})
    (issue,) = issues_of(folder)
    assert "checks.visible and checks.hidden" in issue.message


def test_check_clash_file_versus_directory(make_challenge: ChallengeFactory) -> None:
    folder = make_challenge(files={"workspace/tests": "a file where checks have a dir\n"})
    issues = issues_of(folder)
    assert {issue.message.split("'")[1] for issue in issues} == {"tests"}


# --- solution and hidden checks never reach the workspace or the image ---------------------


def test_hidden_checks_inside_workspace(make_challenge: ChallengeFactory) -> None:
    manifest = replace("  hidden: checks/hidden", "  hidden: workspace/hiddenchecks")
    folder = make_challenge(manifest, files={"workspace/hiddenchecks/test_h.py": "x = 1\n"})
    (issue,) = issues_of(folder)
    assert issue.field == "checks.hidden"
    assert issue.line == line_of(manifest, "  hidden:")
    assert issue.message.startswith("checks.hidden is inside workspace/;")


def test_solution_inside_workspace(make_challenge: ChallengeFactory) -> None:
    manifest = replace("solution: solution/reference.patch", "solution: workspace/reference.patch")
    folder = make_challenge(manifest, files={"workspace/reference.patch": "--- a\n"})
    (issue,) = issues_of(folder)
    assert issue.field == "solution"
    assert issue.line == line_of(manifest, "solution:")
    assert "solution is inside workspace/" in issue.message


def test_hidden_checks_containing_visible(make_challenge: ChallengeFactory) -> None:
    manifest = replace("  hidden: checks/hidden", "  hidden: checks")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == "checks.hidden"
    assert issue.message.startswith("checks.hidden contains checks.visible;")


def test_visible_checks_containing_hidden(make_challenge: ChallengeFactory) -> None:
    manifest = replace("  visible: checks/visible", "  visible: checks")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == "checks.visible"
    assert issue.line == line_of(manifest, "  visible:")
    assert issue.message.startswith("checks.visible contains checks.hidden;")


def test_visible_checks_equal_to_hidden(make_challenge: ChallengeFactory) -> None:
    manifest = replace("  visible: checks/visible", "  visible: checks/hidden")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == "checks.visible"
    assert "is the same path as checks.hidden" in issue.message


def test_visible_checks_pointing_at_solution(make_challenge: ChallengeFactory) -> None:
    manifest = replace("  visible: checks/visible", "  visible: solution")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == "checks.visible"
    assert issue.message.startswith("checks.visible contains solution;")


@pytest.mark.parametrize("visible", ["workspace", "workspace/tests"])
def test_visible_checks_inside_workspace(make_challenge: ChallengeFactory, visible: str) -> None:
    manifest = replace("  visible: checks/visible", f"  visible: {visible}")
    folder = make_challenge(manifest, files={"workspace/tests/test_v.py": "x = 1\n"})
    (issue,) = issues_of(folder)
    assert issue.field == "checks.visible"
    assert "workspace/" in issue.message


@pytest.mark.parametrize(
    ("dockerfile", "files", "leaked"),
    [
        ("Dockerfile", {"Dockerfile": "FROM scratch\n"}, "workspace/"),
        ("checks/Dockerfile", {"checks/Dockerfile": "FROM scratch\n"}, "checks.hidden"),
        ("checks/hidden/Dockerfile", {"checks/hidden/Dockerfile": "FROM scratch\n"}, "hidden"),
        ("solution/Dockerfile", {"solution/Dockerfile": "FROM scratch\n"}, "solution"),
        ("workspace/Dockerfile", {"workspace/Dockerfile": "FROM scratch\n"}, "workspace/"),
    ],
)
def test_build_context_must_not_hold_secrets_or_workspace(
    make_challenge: ChallengeFactory, dockerfile: str, files: dict[str, str | None], leaked: str
) -> None:
    manifest = replace("  dockerfile: environment/Dockerfile", f"  dockerfile: {dockerfile}")
    issues = issues_of(make_challenge(manifest, files=files))
    context_issues = [issue for issue in issues if issue.field == "environment.dockerfile"]
    assert context_issues, issues
    assert all(issue.line == line_of(manifest, "dockerfile:") for issue in context_issues)
    assert any(leaked in issue.message for issue in context_issues)
    assert all("build context" in issue.message for issue in context_issues)


def test_build_context_at_challenge_root_reports_every_leak(
    make_challenge: ChallengeFactory,
) -> None:
    manifest = replace("  dockerfile: environment/Dockerfile", "  dockerfile: Dockerfile")
    issues = issues_of(make_challenge(manifest, files={"Dockerfile": "FROM scratch\n"}))
    assert {issue.field for issue in issues} == {"environment.dockerfile"}
    assert len(issues) == 3  # workspace/, checks.hidden and solution


# --- symlinks and special files ---------------------------------------------------------------


def test_symlink_in_workspace(make_challenge: ChallengeFactory) -> None:
    folder = make_challenge()
    (folder / "workspace" / "src" / "link.py").symlink_to("payments/charge.py")
    (issue,) = issues_of(folder)
    assert issue.file == folder / "workspace"
    assert issue.line is None
    assert issue.field is None
    assert issue.message.startswith("'workspace/src/link.py' is a symlink;")


def test_symlinked_directory_in_hidden_checks(make_challenge: ChallengeFactory) -> None:
    manifest = VALID_CHALLENGE_YAML
    folder = make_challenge()
    (folder / "checks" / "hidden" / "more").symlink_to("tests", target_is_directory=True)
    (issue,) = issues_of(folder)
    assert issue.field == "checks.hidden"
    assert issue.line == line_of(manifest, "  hidden:")
    assert issue.message.startswith("'checks/hidden/more' is a symlink;")
    assert "SECRET_HIDDEN_CONTENT" not in issue.message


def test_fifo_in_visible_checks(make_challenge: ChallengeFactory) -> None:
    folder = make_challenge()
    os.mkfifo(folder / "checks" / "visible" / "pipe")
    (issue,) = issues_of(folder)
    assert issue.field == "checks.visible"
    assert issue.message.startswith("'checks/visible/pipe' is a FIFO;")


def test_unix_socket_in_workspace(make_challenge: ChallengeFactory) -> None:
    folder = make_challenge()
    # AF_UNIX paths are short on macOS, so bind from inside the directory.
    cwd = Path.cwd()
    os.chdir(folder / "workspace")
    try:
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind("s.sock")
            (issue,) = issues_of(folder)
    finally:
        os.chdir(cwd)
    assert issue.message.startswith("'workspace/s.sock' is a socket;")


# --- .git entries -------------------------------------------------------------------------------

GIT_MESSAGE = "is a git repository or git file; challenges must not ship .git"


def test_git_repository_in_workspace_is_reported(make_challenge: ChallengeFactory) -> None:
    # The reviewer's attack: a repo whose filter runs a host command through .gitattributes.
    folder = make_challenge()
    workspace = folder / "workspace"
    marker = folder.parent / "pwned"
    subprocess.run(["git", "init", "-q", str(workspace)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(workspace), "config", "filter.x.clean", f"touch {marker}; cat"],
        check=True,
    )
    (workspace / ".gitattributes").write_text("* filter=x\n")
    (issue,) = issues_of(folder)
    assert issue.file == workspace
    assert issue.line is None
    assert issue.field is None
    assert issue.message == f"'workspace/.git' {GIT_MESSAGE}"
    assert not marker.exists()


@pytest.mark.parametrize(
    ("key", "rel"),
    [
        ("visible", "checks/visible/tests/.GIT"),
        ("hidden", "checks/hidden/deep/er/.Git"),
    ],
)
@pytest.mark.parametrize("as_dir", [True, False], ids=["dir", "file"])
def test_git_entry_in_checks_is_reported(
    make_challenge: ChallengeFactory, key: str, rel: str, as_dir: bool
) -> None:
    folder = make_challenge()
    entry = folder / rel
    entry.parent.mkdir(parents=True, exist_ok=True)
    if as_dir:
        entry.mkdir()
        (entry / "config").write_text("[core]\n")
    else:
        entry.write_text("gitdir: /elsewhere\n")
    (issue,) = issues_of(folder)
    assert issue.field == f"checks.{key}"
    assert issue.line == line_of(VALID_CHALLENGE_YAML, f"  {key}:")
    assert issue.message == f"'{rel}' {GIT_MESSAGE}"


def test_names_merely_containing_git_are_fine(make_challenge: ChallengeFactory) -> None:
    folder = make_challenge(
        files={
            "workspace/.gitignore": "*.pyc\n",
            "workspace/src/x.git": "",
            "workspace/.github/a": "",
        }
    )
    load_challenge(folder)


# --- expected_paths -----------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["src/payments/", "src/payments/charge.py", "new/not/yet"])
def test_expected_paths_relative_to_workspace_need_not_exist(
    make_challenge: ChallengeFactory, value: str
) -> None:
    manifest = replace("expected_paths: [src/payments/]", f"expected_paths: [{value}]")
    challenge = load_challenge(make_challenge(manifest))
    assert challenge.manifest.expected_paths == [value]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("/etc/passwd", "path must be relative to the workspace"),
        ("../outside", "path must stay inside the workspace"),
        ("src/../../x", "path must stay inside the workspace"),
        ("'.'", "path must point inside the workspace, not at the workspace itself"),
        ("'src\\x'", "path must use '/' as separator"),
        ("''", "path must not be empty"),
    ],
)
def test_expected_paths_rules(make_challenge: ChallengeFactory, value: str, message: str) -> None:
    manifest = replace("expected_paths: [src/payments/]", f"expected_paths:\n  - ok/\n  - {value}")
    (issue,) = issues_of(make_challenge(manifest))
    assert issue.field == "expected_paths[1]"
    assert issue.message == message
    assert issue.line == line_of(manifest, f"  - {value}")


# --- packs ------------------------------------------------------------------------------------

VALID_PACK_YAML = """\
spec_version: "0.1"
name: patchground-core
version: 0.1.0
description: Official curated challenges
challenges: [duplicate-charges-on-retry, flaky-cache-ttl]
"""


def test_pack_valid(tmp_path: Path) -> None:
    pack = tmp_path / "patchground-core"
    for name in ("duplicate-charges-on-retry", "flaky-cache-ttl"):
        (pack / name).mkdir(parents=True)
    (pack / "pack.yaml").write_text(VALID_PACK_YAML, encoding="utf-8")
    loaded = load_pack(pack)
    assert loaded.root == pack.resolve()
    assert loaded.manifest.challenges == ["duplicate-charges-on-retry", "flaky-cache-ttl"]


def test_pack_missing_challenge_folder(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    (pack / "duplicate-charges-on-retry").mkdir(parents=True)
    manifest = VALID_PACK_YAML.replace(
        "challenges: [duplicate-charges-on-retry, flaky-cache-ttl]",
        "challenges:\n  - duplicate-charges-on-retry\n  - flaky-cache-ttl\n  - flaky-cache-ttl\n",
    )
    (pack / "pack.yaml").write_text(manifest, encoding="utf-8")
    issues = issues_of(pack, load_pack)
    messages = {(issue.field, issue.line, issue.message) for issue in issues}
    assert ("challenges[1]", 7, "challenge folder 'flaky-cache-ttl' does not exist") in messages
    assert ("challenges[2]", 8, "challenge folder 'flaky-cache-ttl' does not exist") in messages
    assert ("challenges[2]", 8, "challenge 'flaky-cache-ttl' is listed more than once") in messages


def test_pack_missing_manifest(tmp_path: Path) -> None:
    (issue,) = issues_of(tmp_path, load_pack)
    assert issue.message == "pack.yaml not found"
