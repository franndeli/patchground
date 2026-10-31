"""Local challenge discovery: immediate children only, invalid candidates reported, no secrets."""

import os
from pathlib import Path

import pytest

from patchground.packs import (
    DiscoveryError,
    DiscoveryFilters,
    discover_challenges,
    show_challenge,
)
from patchground.spec import ChallengeType, Difficulty

HIDDEN = "SYNTHETIC-HIDDEN-MARKER"
REFERENCE = "SYNTHETIC-REFERENCE-MARKER"


def make_challenge(
    parent: Path,
    name: str,
    *,
    type_: str = "debug",
    difficulty: str = "beginner",
    languages: str = "[python]",
    tags: str = "[pagination]",
) -> Path:
    path = parent / name
    for folder in ("workspace", "checks/visible", "checks/hidden", "environment", "solution"):
        (path / folder).mkdir(parents=True)
    (path / "workspace/code.py").write_text("value = 0\n")
    (path / "checks/visible/test_visible.py").write_text("# visible\n")
    (path / "checks/hidden/test_hidden.py").write_text(f"# {HIDDEN}\n")
    (path / "solution/reference.patch").write_text(REFERENCE)
    (path / "environment/Dockerfile").write_text("FROM scratch\n")
    (path / "TICKET.md").write_text(f"Fix {name}\n")
    (path / "challenge.yaml").write_text(f"""spec_version: "0.1"
id: {name}
version: 1.0.0
title: Title of {name}
type: {type_}
summary: Summary of {name}
languages: {languages}
tags: {tags}
difficulty: {difficulty}
timebox_minutes: 20
ai_policy: allowed
environment:
  dockerfile: environment/Dockerfile
  test_command: run-{HIDDEN}
checks:
  visible: checks/visible
  hidden: checks/hidden
solution: solution/reference.patch
hints: ["{HIDDEN} hint"]
author: {{name: Fixture}}
""")
    return path


def test_empty_directory(tmp_path):
    result = discover_challenges(tmp_path)
    assert result.challenges == ()
    assert result.invalid == ()


def test_defaults_to_current_directory(tmp_path, monkeypatch):
    make_challenge(tmp_path, "alpha")
    monkeypatch.chdir(tmp_path)
    result = discover_challenges()
    assert [item.id for item in result.challenges] == ["alpha"]
    assert result.challenges[0].path == "alpha"


def test_lists_sorted_immediate_children_only(tmp_path):
    make_challenge(tmp_path, "beta")
    make_challenge(tmp_path, "alpha")
    make_challenge(tmp_path / "nested", "deep")
    (tmp_path / "notes.txt").write_text("not a challenge")
    (tmp_path / "plain-folder").mkdir()
    result = discover_challenges(tmp_path)
    assert [item.id for item in result.challenges] == ["alpha", "beta"]
    assert result.invalid == ()


def test_malformed_candidates_are_reported(tmp_path):
    make_challenge(tmp_path, "good")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "challenge.yaml").write_text("id: [unclosed\n")
    (broken / "TICKET.md").write_text("ticket")
    no_ticket = make_challenge(tmp_path, "no-ticket")
    (no_ticket / "TICKET.md").unlink()
    result = discover_challenges(tmp_path, DiscoveryFilters(type=ChallengeType.FEATURE))
    assert result.challenges == ()  # filters apply to valid challenges only
    invalid = {item.name: item for item in result.invalid}
    assert set(invalid) == {"broken", "no-ticket"}
    assert any("challenge.yaml:" in issue for issue in invalid["broken"].issues)
    assert invalid["no-ticket"].issues == ("TICKET.md: not found",)
    assert str(tmp_path) not in "".join(invalid["broken"].issues)


def test_filters(tmp_path):
    make_challenge(tmp_path, "one", type_="debug", difficulty="beginner", languages="[Python]")
    make_challenge(
        tmp_path, "two", type_="feature", difficulty="advanced", languages="[go]", tags="[http]"
    )

    def ids(**kw):
        return [c.id for c in discover_challenges(tmp_path, DiscoveryFilters(**kw)).challenges]

    assert ids(type=ChallengeType.FEATURE) == ["two"]
    assert ids(difficulty=Difficulty.BEGINNER) == ["one"]
    assert ids(lang="python") == ["one"]
    assert ids(tag="HTTP") == ["two"]
    assert ids(lang="go", tag="pagination") == []
    assert ids() == ["one", "two"]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
def test_symlinked_children_are_reported_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    make_challenge(outside, "linked")
    listed = tmp_path / "listed"
    listed.mkdir()
    (listed / "linked").symlink_to(outside / "linked", target_is_directory=True)
    (listed / "file-link").symlink_to(outside / "linked" / "TICKET.md")
    result = discover_challenges(listed)
    assert result.challenges == ()
    assert [item.name for item in result.invalid] == ["linked"]
    assert "symlink" in result.invalid[0].issues[0]


def test_symlinked_manifest_or_ticket_is_invalid(tmp_path):
    challenge = make_challenge(tmp_path, "alpha")
    (tmp_path / "elsewhere.md").write_text("outside ticket")
    (challenge / "TICKET.md").unlink()
    (challenge / "TICKET.md").symlink_to(tmp_path / "elsewhere.md")
    result = discover_challenges(tmp_path)
    assert result.challenges == ()
    assert "symlink" in result.invalid[0].issues[0]
    details = show_challenge(challenge)
    assert not details.valid
    assert details.ticket is None


def test_missing_or_file_directory_is_error(tmp_path):
    with pytest.raises(DiscoveryError):
        discover_challenges(tmp_path / "missing")
    (tmp_path / "file").write_text("x")
    with pytest.raises(DiscoveryError):
        discover_challenges(tmp_path / "file")
    with pytest.raises(DiscoveryError):
        show_challenge(tmp_path / "missing")


def test_show_outputs_metadata_and_ticket_only(tmp_path):
    challenge = make_challenge(tmp_path, "alpha")
    details = show_challenge(challenge)
    assert details.valid
    assert details.challenge is not None
    assert details.challenge.id == "alpha"
    assert details.ticket == "Fix alpha\n"
    assert details.hint_count == 1
    dumped = details.model_dump_json()
    assert HIDDEN not in dumped
    assert REFERENCE not in dumped


def test_show_invalid_folder(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    details = show_challenge(folder)
    assert not details.valid
    assert details.issues == ("challenge.yaml: not found",)


def test_invalid_manifest_does_not_echo_arbitrary_values(tmp_path):
    challenge = make_challenge(tmp_path, "alpha")
    manifest = challenge / "challenge.yaml"
    manifest.write_text(manifest.read_text().replace("type: debug", f"type: {HIDDEN}"))
    details = show_challenge(challenge)
    assert not details.valid
    assert HIDDEN not in details.model_dump_json()
    assert "challenge.yaml:" in details.issues[0]


def test_ticket_replaced_with_fifo_does_not_block(tmp_path, monkeypatch):
    from patchground.packs import discovery

    challenge = make_challenge(tmp_path, "alpha")
    ticket = challenge / "TICKET.md"
    original_open = os.open

    def replace_ticket(path, flags, *args, **kwargs):
        if Path(path) == ticket:
            ticket.unlink()
            os.mkfifo(ticket)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(discovery.os, "open", replace_ticket)
    details = show_challenge(challenge)
    assert not details.valid
    assert "regular file" in details.issues[0]


def test_show_oversized_ticket(tmp_path):
    challenge = make_challenge(tmp_path, "alpha")
    (challenge / "TICKET.md").write_bytes(b"x" * (256 * 1024 + 1))
    details = show_challenge(challenge)
    assert not details.valid
    assert "larger" in details.issues[0]
