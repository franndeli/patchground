from pathlib import Path

import pytest

from patchground.report.analysis import TEXT_LIMIT, diff_evidence, structural_evidence


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path]:
    original, final = tmp_path / "original", tmp_path / "final"
    original.mkdir()
    final.mkdir()
    return original, final


def test_diff_counts_and_scope(trees: tuple[Path, Path]) -> None:
    original, final = trees
    for root in trees:
        (root / "src").mkdir()
        (root / "src/code.py").write_text("one\ntwo\n")
    (final / "src/code.py").write_text("one\nnew\nthree\n")
    (original / "removed.txt").write_text("gone\n")
    (final / "added.txt").write_text("added\n")
    changes = {item.path: item for item in diff_evidence(original, final, ("src/",)).files}
    assert changes["src/code.py"].added_lines == 2
    assert changes["src/code.py"].removed_lines == 1
    assert changes["src/code.py"].outside_expected is False
    assert changes["removed.txt"].kind == "deleted"
    assert changes["added.txt"].outside_expected is True


def test_binary_large_and_ignored_ordinary_files(trees: tuple[Path, Path]) -> None:
    original, final = trees
    (final / "binary").write_bytes(b"\0\xff")
    (final / "large").write_bytes(b"x" * (TEXT_LIMIT + 1))
    (final / ".gitignore").write_text("ordinary\n")
    (final / "ordinary").write_text("included\n")
    (final / ".env").write_text("fake-sensitive-file")
    changes = {item.path: item for item in diff_evidence(original, final, ()).files}
    assert changes["binary"].added_lines is None
    assert changes["large"].removed_lines is None
    assert changes["ordinary"].added_lines == 1
    assert changes["ordinary"].outside_expected is None
    assert ".env" not in changes


def test_executable_change_is_a_file_change(trees: tuple[Path, Path]) -> None:
    original, final = trees
    for root in trees:
        (root / "script").write_text("same\n")
        (root / "script").chmod(0o600)
    (final / "script").chmod(0o700)
    changes = diff_evidence(original, final, ()).files
    assert len(changes) == 1
    assert changes[0].added_lines == changes[0].removed_lines == 0


def test_structural_counts_are_facts(trees: tuple[Path, Path]) -> None:
    original, final = trees
    (original / "test_case.py").write_text(
        "def test_rewrite():\n    assert 1\n    assert 2\ndef test_removed():\n    assert 1\n"
    )
    (final / "test_case.py").write_text("def test_rewrite():\n    assert 1 and 2\n")
    (original / "test_deleted.py").write_text("def test_lost():\n    assert 1\n")
    evidence = structural_evidence(original, final, "pytest -q")
    assert evidence.status == "established"
    assert evidence.removed_files == ("test_deleted.py",)
    assert "test_case.py::test_removed" in evidence.removed_tests
    assert evidence.assertion_reductions[0].before == 2
    assert evidence.assertion_reductions[0].after == 1


def test_vitest_structural_counts_are_explicit_syntax_facts(trees: tuple[Path, Path]) -> None:
    from patchground.runner_assets import VITEST_COMMAND

    original, final = trees
    imports = 'import {test, expect} from "vitest";\n'
    (original / "case.test.ts").write_text(
        imports
        + 'test("kept", () => { expect(1).toBe(1); expect(2).toBe(2) });\n'
        + 'test("removed", () => { expect(1).toBe(1) });'
    )
    (final / "case.test.ts").write_text(
        imports + 'test("kept", () => { expect(true).toBe(true) });'
    )
    evidence = structural_evidence(original, final, VITEST_COMMAND)
    assert evidence.status == "established"
    assert evidence.removed_tests == ("case.test.ts::removed",)
    assert evidence.assertion_reductions[0].before == 2
    assert evidence.assertion_reductions[0].after == 1
    assert "expect-call" in evidence.reason
    (final / "case.test.ts").write_text(imports + 'test.skip("kept", () => {});')
    assert structural_evidence(original, final, VITEST_COMMAND).status == "not_established"


def test_unsupported_structure_is_not_claimed(trees: tuple[Path, Path]) -> None:
    original, final = trees
    assert structural_evidence(original, final, "npm test").status == "not_established"
    (final / "test_bad.py").write_text("not valid python!")
    assert structural_evidence(original, final, "pytest").status == "not_established"
